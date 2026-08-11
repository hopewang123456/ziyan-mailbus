"""
ziyan-mailbus 工具函数

文件锁、JSON 读写、日志、消息构建等通用工具。
"""

import json
import os
import sys
import shutil
import copy
import time
import contextlib
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from lib.infra.clock import now_dt, now_iso, now_ts, now_utc_dt
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from lib.domain.models import Message, MsgStatus, Priority, MsgType, Level, generate_msg_id
from .constants import (
    _now_iso,
    MAILBUS_ROOT_STR,
    MAILBUS_SKILLS_ROOT_STR,
    MAILBUS_IDENTITIES_ROOT_STR,
    TEAM_PACK_ROOT_STR,
    TEAM_PACK_SKILLS_ROOT_STR,
)

# Store-relative path markers for to_container_store_path (§10 #40).
CONTAINER_STORE_MARKERS: tuple[str, ...] = (
    "msg-files/",
    "msg-results/",
    "inbox/",
    "rules/",
    "tasks/",
    "work-orders/",
    "deliverables/",
    "human-queue",
    "agentmemory-pending/",
    "locks/",
    "patches/",
    "replies/",
)


def configure_stdio_utf8() -> None:
    """Windows GBK 控制台输出 emoji/Unicode 时避免 UnicodeEncodeError。"""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


# ── 路径常量 ──────────────────────────────────────────────────────────

def _ensure_dir(path: str) -> str:
    """确保目录存在，返回原路径"""
    os.makedirs(path, exist_ok=True)
    return path


def to_wsl_path(path: str) -> str:
    """Windows 绝对路径 → WSL /mnt/ 路径（供 wsl -e bash 调用脚本）。"""
    p = (path or "").strip().replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:]
    p = os.path.abspath(p).replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:]
    return p


def to_container_store_path(data_dir: str, path: str) -> str:
    """宿主机 store 路径 → 容器内 /mailbus/store/...（Docker/WSL 挂载）。"""
    if not path:
        return path
    norm = path.replace("\\", "/")
    if norm.startswith("/mailbus/"):
        return norm
    dd = os.path.abspath(data_dir).replace("\\", "/").rstrip("/")
    ap = os.path.abspath(path).replace("\\", "/")
    if ap.lower().startswith(dd.lower() + "/"):
        rel = ap[len(dd):].lstrip("/")
        return f"/mailbus/store/{rel}"
    for marker in CONTAINER_STORE_MARKERS:
        idx = ap.lower().find(marker)
        if idx >= 0:
            return "/mailbus/store/" + ap[idx:]
    return path


def rewrite_host_store_refs(data_dir: str, text: str, agent_cfg: dict) -> str:
    """推送正文内宿主机 store 路径 → /mailbus/store（Docker agent）。"""
    if not text:
        return text or ""
    from lib.adapters.frameworks import get_adapter

    adapter = get_adapter((agent_cfg or {}).get("type", ""))
    if not adapter or not adapter.container_service:
        return text
    out = text
    dd_abs = os.path.abspath(data_dir)
    variants = {
        dd_abs,
        dd_abs.replace("\\", "/"),
        to_wsl_path(dd_abs),
    }
    for v in variants:
        if v:
            out = out.replace(v, "/mailbus/store")
            out = out.replace(v.replace("/", "\\"), "/mailbus/store")
    out = out.replace("/mailbus/store\\", "/mailbus/store/")
    while "\\" in out and "/mailbus/store/" in out:
        out = out.replace("\\", "/")
    return out


def format_push_content_for_agent(data_dir: str, content: str, agent_cfg: dict) -> str:
    """推送正文框架入口：容器 agent 路径统一 rewrite。"""
    return rewrite_host_store_refs(data_dir, content or "", agent_cfg or {})


def resolve_mailbus_path(data_dir: str, ref: str) -> str:
    """将 config 中的 Docker/WSL 路径解析为本地绝对路径。"""
    if not ref or not isinstance(ref, str):
        return ""
    ref = ref.strip().replace("\\", "/")
    if os.path.isfile(ref):
        return ref
    root = MAILBUS_ROOT_STR if os.path.isdir(os.path.join(MAILBUS_ROOT_STR, "access")) else os.path.dirname(os.path.abspath(data_dir))
    # WSL: /mnt/e/... → E:\...
    if ref.startswith("/mnt/e/"):
        win = "E:" + ref[7:].replace("/", os.sep)
        if os.path.isfile(win):
            return win
        # mail 仓库内 identities 回退
        tail = ref.split("/ai_tools/mail/", 1)[-1] if "/ai_tools/mail/" in ref else ref.split("/mailbus/", 1)[-1] if "/mailbus/" in ref else ""
        if tail:
            cand = os.path.join(root, tail.replace("/", os.sep))
            if os.path.isfile(cand):
                return cand
    if ref.startswith("team-pack/"):
        cand = os.path.join(TEAM_PACK_ROOT_STR, ref[len("team-pack/"):].replace("/", os.sep))
        if os.path.isfile(cand):
            return cand
        # team-pack 知识子树可单独改根
        if ref.startswith("team-pack/skills/"):
            cand = os.path.join(
                TEAM_PACK_SKILLS_ROOT_STR,
                ref[len("team-pack/skills/"):].replace("/", os.sep),
            )
            if os.path.isfile(cand):
                return cand
    if ref.startswith("mailbus-core/") or ref.startswith("mail/"):
        prefix = "mailbus-core/" if ref.startswith("mailbus-core/") else "mail/"
        tail = ref[len(prefix):]
        cand = os.path.join(MAILBUS_ROOT_STR, tail.replace("/", os.sep))
        if os.path.isfile(cand):
            return cand
        if tail.startswith("skills/"):
            cand = os.path.join(MAILBUS_SKILLS_ROOT_STR, tail[len("skills/"):].replace("/", os.sep))
            if os.path.isfile(cand):
                return cand
        if tail.startswith("identities/"):
            cand = os.path.join(
                MAILBUS_IDENTITIES_ROOT_STR,
                tail[len("identities/"):].replace("/", os.sep),
            )
            if os.path.isfile(cand):
                return cand
    if ref.startswith("/mailbus/store/"):
        return os.path.join(data_dir, ref[len("/mailbus/store/"):].replace("/", os.sep))
    if ref.startswith("/mailbus/"):
        return os.path.join(root, ref[len("/mailbus/"):].replace("/", os.sep))
    if ref.startswith("store/"):
        return os.path.join(root, ref.replace("/", os.sep))
    local = os.path.join(root, ref.lstrip("/").replace("/", os.sep))
    return local


def identity_candidates(data_dir: str, agent: str, configured: str = "") -> list[str]:
    """identity 文件候选路径（Docker / WSL / 本地）。"""
    root = os.path.dirname(os.path.abspath(data_dir))
    cands: list[str] = []
    if configured:
        cands.append(resolve_mailbus_path(data_dir, configured))
    cands.append(
        os.path.join(TEAM_PACK_SKILLS_ROOT_STR, "roles", "overlays", agent, "SKILL.md")
    )
    cands.append(os.path.join(MAILBUS_IDENTITIES_ROOT_STR, agent, "SOUL.md"))
    cands.append(os.path.join(MAILBUS_IDENTITIES_ROOT_STR, f"{agent}-soul.md"))
    cands.append(os.path.join(MAILBUS_IDENTITIES_ROOT_STR, f"{agent}.md"))
    out, seen = [], set()
    for p in cands:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_paths(data_dir: str) -> dict:
    """
    根据 data_dir 解析所有子目录路径。
    返回 {"inbox", "queue_urgent", "queue_normal", "archive", "errors", "sent", "board", "config"}
    """
    return {
        "inbox":       _ensure_dir(f"{data_dir}/inbox"),
        "queue_urgent": _ensure_dir(f"{data_dir}/queue/urgent"),
        "queue_normal": _ensure_dir(f"{data_dir}/queue/normal"),
        "archive":     _ensure_dir(f"{data_dir}/archive"),
        "errors":      _ensure_dir(f"{data_dir}/errors"),
        "sent":        f"{data_dir}/sent.json",
        "board":       f"{data_dir}/board.json",
        "config":      f"{data_dir}/config.json",
    }


# ── 文件锁 ────────────────────────────────────────────────────────────

import hashlib

_LOCK_ROOT = os.environ.get("MAILBUS_LOCK_DIR") or (
    tempfile.gettempdir() if sys.platform == "win32" else "/tmp"
)
GLOBAL_LOCK_FILE = os.path.join(_LOCK_ROOT, "ziyan-mailbus.lock")


def get_lock_root() -> str:
    """Mailbus 文件锁根目录（Windows 为 %TEMP%，Unix 为 /tmp）。"""
    return _LOCK_ROOT


def _lock_path(path: str = "") -> str:
    """生成锁文件路径：有 path 用 per-file 锁，否则用全局锁。"""
    if path:
        h = hashlib.sha256(path.encode()).hexdigest()[:16]
        return os.path.join(_LOCK_ROOT, f"ziyan-mailbus-{h}.lock")
    return GLOBAL_LOCK_FILE


def _try_acquire_lock(lock_fd, *, non_blocking: bool = True) -> bool:
    if sys.platform == "win32":
        try:
            msvcrt.locking(
                lock_fd.fileno(),
                msvcrt.LK_NBLCK if non_blocking else msvcrt.LK_LOCK,
                1,
            )
            return True
        except OSError:
            return False
    flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if non_blocking else 0)
    try:
        fcntl.flock(lock_fd, flags)
        return True
    except BlockingIOError:
        return False


def _release_lock(lock_fd) -> None:
    if sys.platform == "win32":
        try:
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _open_lock_file(lock_file: str, *, retries: int = 8):
    """打开锁文件；Windows 上多进程争用 Temp 时 PermissionError 可重试。"""
    last_err: OSError | None = None
    for attempt in range(retries):
        try:
            return open(lock_file, "a+")
        except PermissionError as exc:
            last_err = exc
            time.sleep(0.15 * (attempt + 1))
    if last_err is not None:
        raise last_err
    return open(lock_file, "a+")


@contextlib.contextmanager
def file_lock(timeout: float = 10.0, path: str = ""):
    """文件锁 — 防止多个进程同时写同一份文件（带超时，防死锁）"""
    os.makedirs(_LOCK_ROOT, exist_ok=True)
    lock_file = _lock_path(path)
    lock_fd = _open_lock_file(lock_file)
    deadline = now_ts() + timeout
    acquired = False
    try:
        while now_ts() < deadline:
            if _try_acquire_lock(lock_fd, non_blocking=True):
                acquired = True
                break
            time.sleep(0.1)
        if not acquired:
            fallback = GLOBAL_LOCK_FILE
            if lock_file != fallback:
                lock_fd.close()
                lock_fd = open(fallback, "w")
                deadline2 = now_ts() + 5.0
                while now_ts() < deadline2:
                    if _try_acquire_lock(lock_fd, non_blocking=True):
                        acquired = True
                        break
                    time.sleep(0.1)
            if not acquired:
                raise TimeoutError(f"无法获取文件锁 (path={path}, timeout={timeout}s)")
        yield
    except Exception:
        raise
    finally:
        if acquired:
            _release_lock(lock_fd)
        lock_fd.close()
        if lock_file != GLOBAL_LOCK_FILE:
            try:
                os.unlink(lock_file)
            except OSError:
                pass


@contextlib.contextmanager
def named_lock(name: str, *, blocking: bool = False, timeout: float = 10.0):
    """进程级命名锁（如 mailbus-scan）。"""
    os.makedirs(_LOCK_ROOT, exist_ok=True)
    path = os.path.join(_LOCK_ROOT, f"{name}.lock")
    lock_fd = open(path, "w")
    acquired = False
    deadline = now_ts() + (timeout if blocking else 0.0)
    try:
        while True:
            if _try_acquire_lock(lock_fd, non_blocking=not blocking):
                acquired = True
                break
            if not blocking:
                break
            if now_ts() >= deadline:
                break
            time.sleep(0.05)
        yield acquired
    finally:
        if acquired:
            _release_lock(lock_fd)
        lock_fd.close()


# ── JSON 读写 ─────────────────────────────────────────────────────────

# 内存缓存：{filepath: (data, expiry_timestamp)}
# 用于 json_read 高频调用场景，TTL=5秒
# 注意：缓存的 data 必须是 deep-copy，因为调用方可能会修改返回的 dict
_JSON_CACHE: dict = {}


def clear_json_cache():
    """清空 json_read 的内存缓存（主要用于测试场景）"""
    _JSON_CACHE.clear()


def _cleanup_bak_files(filepath: str, max_keep: int = 5):
    """清理 filepath 对应的 .bak 文件，只保留最新的 max_keep 个"""
    import glob
    pattern = filepath + ".bak.*"
    baks = sorted(glob.glob(pattern), key=os.path.getmtime)
    while len(baks) > max_keep:
        old = baks.pop(0)
        try:
            os.remove(old)
        except OSError:
            pass


def json_read(filepath: str, default: Any = None, ttl: float = 5.0) -> Any:
    """读 JSON 文件（带锁 + 内存缓存），遇到损坏 JSON 尝试修复"""
    now = now_ts()
    cached = _JSON_CACHE.get(filepath)
    if cached is not None:
        data, expiry, cached_mtime = cached
        if now < expiry:
            try:
                current_mtime = os.path.getmtime(filepath)
            except OSError:
                current_mtime = None
            if current_mtime == cached_mtime:
                return copy.deepcopy(data)

    with file_lock(path=filepath):
        try:
            file_mtime = os.path.getmtime(filepath)
        except OSError:
            file_mtime = None
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            _JSON_CACHE[filepath] = (data, now + ttl, file_mtime)
            return copy.deepcopy(data)
        except FileNotFoundError:
            return default
        except UnicodeDecodeError:
            try:
                with open(filepath, encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                json_write(filepath, data)
                _JSON_CACHE[filepath] = (data, now + ttl, file_mtime)
                return copy.deepcopy(data)
            except Exception:
                return default
        except json.JSONDecodeError:
            # JSON 损坏 → 尝试修复（常见问题：content 里有未转义的双引号）
            try:
                with open(filepath, encoding="utf-8") as f:
                    raw = f.read()
                # 尝试用 strict=False 模式解析
                import re
                fixed = json.loads(raw, strict=False)
                # 修复成功，写回
                json_write(filepath, fixed)
                return fixed
            except (json.JSONDecodeError, Exception):
                # 修复失败 → 备份损坏文件（最多保留5个）
                _cleanup_bak_files(filepath, max_keep=5)
                bak = filepath + f".bak.{int(now_ts())}"
                try:
                    shutil.copy2(filepath, bak)
                except OSError:
                    pass
                return default


def json_write(filepath: str, data: Any, indent: int = 2):
    """写 JSON 文件（带锁，原子写入）"""
    tmp = filepath + ".tmp"
    with file_lock(path=filepath):
        # 确保目标目录存在（防止并发删除导致的 FileNotFoundError）
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, filepath)
        except Exception:
            # 如果写入过程中被中断（如进程被 kill），清理残留 tmp 文件
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except OSError:
                pass
            raise
    # 写入后清除缓存，确保下次读取拿到最新数据
    _JSON_CACHE.pop(filepath, None)


def jsonl_append(filepath: str, entry: dict):
    """追加一条 JSON Lines 记录"""
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with file_lock(path=filepath):
        with open(filepath, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
    # 追加写入后清除缓存
    _JSON_CACHE.pop(filepath, None)


# ── 日志 ──────────────────────────────────────────────────────────────

def log_error(errors_dir: str, msg_id: str, to: str, error: str, level: str = Level.ERROR):
    """写一条错误日志到 errors/ 目录（按周分文件）"""
    week = now_dt().strftime("%Y-W%V")
    filepath = f"{errors_dir}/{week}.jsonl"
    entry = {
        "ts": _now_iso(),
        "level": level,
        "msg_id": msg_id,
        "to": to,
        "error": error,
    }
    jsonl_append(filepath, entry)


def build_message(
    from_: str,
    to: str,
    content: str,
    msg_type: str = MsgType.NOTICE,
    priority: str = Priority.NORMAL,
    attachments: Optional[list] = None,
    forward_to: Optional[list] = None,
    task: Optional[dict] = None,
    timeout_minutes: Optional[int] = None,
    escalate_to: Optional[str] = None,
    project: Optional[str] = None,  # v4.0
) -> Message:
    """构建一条新消息，自动生成 ID、时间、reply_format、action"""
    msg_id = generate_msg_id()
    priority = Priority.URGENT if is_content_urgent(content, priority) else priority
    reply_format = _build_reply_format(to, msg_id)

    # 构建 action
    action = dict(MsgType.default_action(msg_type))
    # reply_to = None 表示需要回复发件人，__post_init__ 会自动填
    if forward_to:
        action["forward_to"] = forward_to

    # 自动生成 actions 清单（task 类型）
    actions_list = []
    if task and task.get("summary"):
        # 从 task.summary 拆解步骤（按换行或序号）
        summary = task["summary"]
        import re
        # 尝试按序号拆分（1. xxx / 2. xxx）
        steps = re.findall(r'(?:^|\n)\s*(?:\d+[\.\、])\s*([^\n]+)', summary)
        if not steps:
            # 尝试按换行拆分
            steps = [s.strip() for s in summary.split("\n") if s.strip()]
        if not steps:
            # 整段作为一个步骤
            steps = [summary[:80]]
        for step in steps:
            actions_list.append({"step": step.strip()[:100], "status": "pending"})
    
    msg = Message(
        id=msg_id,
        from_=from_,
        to=to,
        content=content,
        type=msg_type,
        priority=priority,
        attachments=attachments or [],
        reply_format=reply_format,
        action=action,
        task=task,
        status=MsgStatus.PENDING,
        created_at=_now_iso(),
        timeout_minutes=timeout_minutes,
        escalate_to=escalate_to,
        project=project,
    )
    if actions_list:
        msg.actions = actions_list
    return msg


# ── Registry 加载 / Domain 路由 ──────────────────────────────────────


DEFAULT_REGISTRY_PATH = None  # 由 data_dir 推导


def _registry_path(data_dir: str) -> str:
    """获取 registry.json 的路径（默认在 data_dir 同级）"""
    return os.path.join(data_dir, "registry.json")


_REGISTRY_CACHE: dict = {}


def load_registry(data_dir: str) -> dict:
    """
    加载 registry.json。
    
    返回: {"version": "1", "agents": {name: {domains, role, skills}}}
    文件不存在返回空 registry。
    """
    rpath = _registry_path(data_dir)
    global _REGISTRY_CACHE
    if rpath in _REGISTRY_CACHE:
        return _REGISTRY_CACHE[rpath]
    
    rdata = json_read(rpath, {})
    agents = rdata.get("agents", {})
    result = {"version": rdata.get("version", "1"), "agents": agents}
    _REGISTRY_CACHE[rpath] = result
    return result


def clear_registry_cache():
    """清空 registry 缓存（测试用）"""
    global _REGISTRY_CACHE
    _REGISTRY_CACHE = {}


def resolve_domain_to_agents(domain: str, registry: dict) -> list:
    """
    根据 domain 解析对应的 agent 列表。
    
    参数:
        domain: domain 名称（如 "engineering"）
        registry: load_registry() 返回的 registry 数据
    
    返回: agent 名称列表（去重、按字母序）
    """
    agents = {}
    for name, info in registry.get("agents", {}).items():
        domains = info.get("domains", [])
        if domain in domains:
            agents[name] = True
        if domain == "ALL" and domains:
            agents[name] = True
    
    return sorted(agents.keys())


def is_content_urgent(content: str, priority: str) -> bool:
    """检查是否需要标记为加急"""
    if priority == Priority.URGENT:
        return True
    if "紧急" in content:
        return True
    return False


def _build_reply_format(to: str, msg_id: str, data_dir: str = None) -> dict:
    """构建消息附带的回复格式说明"""
    from .constants import DEFAULT_DATA_DIR
    inbox_base = (data_dir + "/inbox") if data_dir else (DEFAULT_DATA_DIR + "/inbox")
    return {
        "ack": {
            "file": f"{inbox_base}/{to}/ack.json",
            "format": {"action": "ack", "msg_id": msg_id, "agent": to, "timestamp": "<ISO时间>"},
        },
        "mark_read": {
            "format": {"action": "mark_read", "msg_ids": [msg_id], "agent": to, "timestamp": "<ISO时间>"},
        },
        "forward": {
            "description": "如需转发给其他 agent，写文件到目标 inbox",
            "target_format": f"{inbox_base}/<目标agent>/inbox.json",
            "format": {
                "action": "forward",
                "original_msg_id": msg_id,
                "from": to,
                "to": "<目标agent>",
                "type": "normal",
                "priority": "normal",
                "content": "...",
                "attachments": [],
                "timestamp": "<ISO时间>",
            },
        },
    }
