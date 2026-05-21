"""
ziyan-mailbus 工具函数

文件锁、JSON 读写、日志、消息构建等通用工具。
"""

import json
import os
import fcntl
import shutil
import contextlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from .models import Message, MsgStatus, Priority, MsgType, Level, generate_msg_id, _now_iso

# ── 路径常量 ──────────────────────────────────────────────────────────

def _ensure_dir(path: str) -> str:
    """确保目录存在，返回原路径"""
    os.makedirs(path, exist_ok=True)
    return path


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

LOCK_FILE = "/tmp/ziyan-mailbus.lock"


@contextlib.contextmanager
def file_lock():
    """文件锁 — 防止多个 cron 进程同时写同一份文件"""
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    except Exception:
        raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


# ── JSON 读写 ─────────────────────────────────────────────────────────

def json_read(filepath: str, default: Any = None) -> Any:
    """读 JSON 文件（带锁）"""
    with file_lock():
        try:
            with open(filepath) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default


def json_write(filepath: str, data: Any, indent: int = 2):
    """写 JSON 文件（带锁，原子写入）"""
    tmp = filepath + ".tmp"
    with file_lock():
        with open(tmp, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, filepath)


def jsonl_append(filepath: str, entry: dict):
    """追加一条 JSON Lines 记录"""
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with file_lock():
        with open(filepath, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()


# ── 日志 ──────────────────────────────────────────────────────────────

def log_error(errors_dir: str, msg_id: str, to: str, error: str, level: str = Level.ERROR):
    """写一条错误日志到 errors/ 目录（按周分文件）"""
    week = datetime.now().strftime("%Y-W%V")
    filepath = f"{errors_dir}/{week}.jsonl"
    entry = {
        "ts": _now_iso(),
        "level": level,
        "msg_id": msg_id,
        "to": to,
        "error": error,
    }
    jsonl_append(filepath, entry)


# ── 消息构建 ──────────────────────────────────────────────────────────

def build_message(
    from_: str,
    to: str,
    content: str,
    msg_type: str = MsgType.NOTICE,
    priority: str = Priority.NORMAL,
    attachments: Optional[list] = None,
) -> Message:
    """构建一条新消息，自动生成 ID、时间、reply_format"""
    msg_id = generate_msg_id()
    priority = Priority.URGENT if is_content_urgent(content, priority) else priority
    reply_format = _build_reply_format(to, msg_id)
    return Message(
        id=msg_id,
        from_=from_,
        to=to,
        content=content,
        type=msg_type,
        priority=priority,
        attachments=attachments or [],
        reply_format=reply_format,
        status=MsgStatus.PENDING,
        created_at=_now_iso(),
    )


def is_content_urgent(content: str, priority: str) -> bool:
    """检查是否需要标记为加急"""
    if priority == Priority.URGENT:
        return True
    if "紧急" in content:
        return True
    return False


def _build_reply_format(to: str, msg_id: str) -> dict:
    """构建消息附带的回复格式说明"""
    inbox_base = "/mnt/e/ai_tools/mail/store/inbox"
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
