"""
ziyan-mailbus pusher

从队列读取待推送消息，通过 CLI 推送给 agent，等待 ack。
"""

import os
import subprocess
import sys
import time
import random
from typing import Optional
from pathlib import Path

from lib.adapters.clock import now_dt, now_iso, now_ts, now_utc_dt
from .models import Message, MsgStatus, Priority, MsgType
from .constants import DEFAULT_CLI_MSG_MAX_CHARS
from .utils import json_read, json_write, jsonl_append, log_error, resolve_paths, _now_iso
from lib.scan import mark_as_pushed, update_message_status
from .mbus_log import debug, warn

# agent_name -> subprocess.Popen（后台 CLI，供超时 kill / 自愈查询）
_ACTIVE_CLI_PROCS: dict[str, subprocess.Popen] = {}


def get_active_cli_proc(agent_name: str) -> subprocess.Popen | None:
    """返回 agent 当前后台 CLI 进程（若仍存活）。"""
    proc = _ACTIVE_CLI_PROCS.get(agent_name)
    if proc is None:
        return None
    if proc.poll() is not None:
        _ACTIVE_CLI_PROCS.pop(agent_name, None)
        return None
    return proc


def _register_cli_proc(agent_name: str, proc: subprocess.Popen) -> None:
    old = _ACTIVE_CLI_PROCS.get(agent_name)
    if old is not None and old.poll() is None and old.pid != proc.pid:
        try:
            old.kill()
            old.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        except Exception as exc:
            warn(f"[pusher] replaced stale CLI pid={getattr(old, 'pid', '?')}: {exc}")
    _ACTIVE_CLI_PROCS[agent_name] = proc


def _kill_cli_proc(proc: subprocess.Popen, agent_name: str = "") -> None:
    """终止超时 CLI 并 reap，避免孤儿进程重复 push。"""
    try:
        proc.kill()
        proc.communicate()
    except Exception as exc:
        warn(f"[pusher] kill CLI {agent_name or proc.pid}: {exc}")
    if agent_name:
        _ACTIVE_CLI_PROCS.pop(agent_name, None)


# ── API Key 注入 ─────────────────────────────────────────────────────
# P0: 统一从 .env 文件加载所有 API Key，注入子进程
# 不再通过 cmd 字面量搜索 provider 名（那不可靠）
_ENV_LOADED = False
_ALL_ENV_KEYS = {}

# 已知 API Key 变量名列表（扩展时在此追加）
KNOWN_API_KEYS = [
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "QWEN_API_KEY",
    "ZHIPU_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "TOGETHER_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
]


def _load_env():
    """加载 mailbus 项目目录下的 .env 文件，缓存所有环境变量"""
    global _ENV_LOADED, _ALL_ENV_KEYS
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    # 先继承父进程已有的 API Key 环境变量
    _ALL_ENV_KEYS.update({k: v for k, v in os.environ.items() if k.endswith("_API_KEY")})

    # 搜索路径：项目 .env → 容器内 Hermes → HERMES_DATA → ~/.hermes/.env
    bus_dir = Path(__file__).resolve().parent.parent  # mailbus/lib/ → mailbus/
    hermes_data = os.environ.get("HERMES_DATA", "").strip()
    candidates = [
        bus_dir / ".env",
        Path("/run/hermes/.env"),
        Path("/home/hermes/.hermes/.env"),
        Path("/home/administrator/.hermes/.env"),
    ]
    if hermes_data:
        candidates.append(Path(hermes_data) / ".env")
    candidates.append(Path.home() / ".hermes" / ".env")
    for env_path in candidates:
        if env_path.exists():
            with open(env_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if val:
                        _ALL_ENV_KEYS[key] = val
            break  # 找到第一个有效的 .env 就停


def get_env_for_cli(cmd: str = "") -> dict:
    """给 CLI 命令补充所有已知的 API Key 环境变量

    P0 增强：不再通过 cmd 中查找 provider 名来推测需要什么 key，
    而是统一注入所有已知的 API Key，确保子进程总是能用。
    如果某个 key 不存在于 .env 中，就不注入——不产生坏影响。
    """
    _load_env()
    extra_env = {}
    for key in KNOWN_API_KEYS:
        if key in _ALL_ENV_KEYS:
            extra_env[key] = _ALL_ENV_KEYS[key]
    return extra_env


def _truncate_cli_text(text: str, max_chars: int = DEFAULT_CLI_MSG_MAX_CHARS) -> str:
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars] + "\n...(内容已截断，完整见 inbox / msg-files)"


def _wrap_docker_cmd(cmd: str) -> str:
    """保留兼容：非 Windows 或无 wsl 时仍返回 shell 字符串。"""
    argv = _docker_push_argv(cmd)
    if argv:
        return cmd
    import shutil
    stripped = (cmd or "").lstrip()
    if not stripped.startswith("docker "):
        return cmd
    if shutil.which("docker"):
        return cmd
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl:
        return f"{wsl} {stripped}"
    return cmd


def _docker_push_argv(cmd: str) -> list[str] | None:
    """Windows 无 docker 时返回 [wsl, bash, -lc, <docker cmd>]，供 Popen(shell=False)。"""
    import shutil
    import sys

    stripped = (cmd or "").lstrip()
    if sys.platform != "win32" or not stripped.startswith("docker "):
        return None
    if shutil.which("docker"):
        return None
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return None
    return [wsl, "bash", "-lc", stripped]


def _push_argv(cmd: str) -> list[str] | None:
    """Windows 下统一 argv 启动（配合 CREATE_NO_WINDOW），消除 shell=True 黑窗。"""
    import shlex
    import shutil
    import sys

    argv = _docker_push_argv(cmd)
    if argv:
        return argv
    stripped = (cmd or "").lstrip()
    if not stripped:
        return None
    if sys.platform != "win32":
        return None
    if stripped.startswith("docker ") and shutil.which("docker"):
        return shlex.split(stripped, posix=False)
    # 必须用绝对路径：CREATE_NO_WINDOW / 精简 PATH 下相对 cmd.exe 会 WinError 2
    comspec = (
        os.environ.get("ComSpec")
        or shutil.which("cmd.exe")
        or shutil.which("cmd")
        or r"C:\Windows\System32\cmd.exe"
    )
    return [comspec, "/c", stripped]


def _popen_no_window_kwargs() -> dict:
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flags:
            return {"creationflags": flags}
    return {}


def push_messages(
    data_dir: str,
    agent_name: str,
    messages: list,
    cli_cmd: list = None,
    ack_timeout: int = 30,
    max_retries: int = 3,
    auto_ack: bool = False,
) -> list:
    """
    推送给指定 agent 多条消息。
    
    参数:
        data_dir: 数据目录
        agent_name: agent 名称
        messages: 消息列表（Message 对象或 dict）
        cli_cmd: CLI 命令模板（空字符串 = 仅文件通信，不等待 ack）
                 模板中的 'MSG' 占位符会被替换为实际消息内容
        ack_timeout: 未使用（保留参数兼容）
        max_retries: 最大重试次数
        auto_ack: 推送成功后直接标记为 acknowledged（用于 Hermes 等不写 ack 的 agent）
    
    返回:
        推送失败的消息 ID 列表（推送成功即视为送达，不等待 ack）
    """
    failed_ids = []
    msg_ids = [m.id if not isinstance(m, dict) else m["id"] for m in messages]
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agent_cfg_entry = (cfg.get("agents") or {}).get(agent_name) or {}
    if agent_cfg_entry.get("available") is False:
        return []
    paths = resolve_paths(data_dir)
    
    # 0. 幂等去重：检查这些消息是否已经被 agent ack 过
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if inbox_data:
        from lib.scan import _get_acked_ids
        acked_ids = _get_acked_ids(inbox_data)
        already_acked = [mid for mid in msg_ids if mid in acked_ids]
        if already_acked:
            for mid in already_acked:
                update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
            remaining = [mid for mid in msg_ids if mid not in acked_ids]
            if not remaining:
                return []
            msg_ids = remaining
            messages = [m for m in messages if (m.id if not isinstance(m, dict) else m["id"]) in msg_ids]
    
    # 1. 标记为 pushed
    mark_as_pushed(data_dir, agent_name, msg_ids)
    
    # 如果没有 CLI 配置，走纯文件通信 — 标记为 pushed，等待 agent 自检后写 ack
    if not cli_cmd:
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []
    
    # 2. 构建推送文本（从 Message.action 结构化字段读取指令）
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents_cfg = cfg.get("agents", {})
    from .token_budget import load_token_budget
    from lib.adapters.frameworks import store_path_for_agent
    from .utils import format_push_content_for_agent

    agent_cfg_entry = agents_cfg.get(agent_name) or {}
    tb = load_token_budget(cfg)
    rules_dir = store_path_for_agent(data_dir, f"{data_dir}/rules", agent_cfg_entry)
    inbox_path = store_path_for_agent(data_dir, f"{data_dir}/inbox/{agent_name}/inbox.json", agent_cfg_entry)
    ack_path = store_path_for_agent(data_dir, f"{data_dir}/inbox/{agent_name}/ack.json", agent_cfg_entry)
    system_context = (
        f"mailbus | agent={agent_name}\n"
        f"inbox={inbox_path}\n"
        f"ack={ack_path}\n"
        f"rules={rules_dir}/\n---\n"
    )
    combined_text = system_context

    per_msg_max = int(
        (agents_cfg.get(agent_name) or {}).get("cli_msg_max_chars")
        or tb.get("cli_msg_max_chars")
        or DEFAULT_CLI_MSG_MAX_CHARS
    )
    combined_max = int(tb.get("cli_combined_max_chars") or 4000)

    for msg_entry in messages:
        from_ = msg_entry.get("from", "?") if isinstance(msg_entry, dict) else msg_entry.from_
        content = msg_entry.get("content", "") if isinstance(msg_entry, dict) else msg_entry.content
        entry_dict = msg_entry if isinstance(msg_entry, dict) else msg_entry.to_dict()
        agent_cfg_entry = agents_cfg.get(agent_name) or {}
        raw_content = content or ""
        raw_content = format_push_content_for_agent(data_dir, raw_content, agent_cfg_entry)
        content = _truncate_cli_text(raw_content, max_chars=per_msg_max)
        msg_id = msg_entry.get("id", "") if isinstance(msg_entry, dict) else msg_entry.id
        action_raw = msg_entry.get("action", {}) if isinstance(msg_entry, dict) else (msg_entry.action or MsgType.default_action(msg_entry.type))
        msg_type = msg_entry.get("type", "notice") if isinstance(msg_entry, dict) else msg_entry.type
        fwd_chain = msg_entry.get("forward_chain") if isinstance(msg_entry, dict) else msg_entry.forward_chain

        agent_type = agent_cfg_entry.get("type", "")
        from .file_task_push import (
            build_file_task_push_body,
            ensure_file_task_work_order,
            should_file_task_push,
        )
        if should_file_task_push(agent_type, agent_cfg_entry, entry_dict, raw_content):
            _, wo_path, rf_path = ensure_file_task_work_order(data_dir, agent_name, entry_dict)
            wo_path = store_path_for_agent(data_dir, wo_path, agent_cfg_entry)
            rf_path = store_path_for_agent(data_dir, rf_path, agent_cfg_entry)
            msg_body = build_file_task_push_body(
                from_=from_, msg_id=msg_id, msg_type=msg_type,
                wo_path=wo_path, result_path=rf_path,
            )
        else:
            # 追踪链
            chain_text = ""
            if fwd_chain and fwd_chain.get("hops"):
                hops = fwd_chain["hops"]
                chain_text = " | ".join([f"{h.get('agent','?')}:{h.get('action','?')}" for h in hops])
                chain_text = f" [链: {chain_text}]"

            # 精简消息体
            msg_body = f"📬 {msg_type} | {from_} | id={msg_id}{chain_text}\n{content}\n"

            reply_to = action_raw.get("reply_to", "") if action_raw else ""
            if reply_to and reply_to not in ("mailbus", "broadcast", "system", "manual", "mailbus-test", "test", ""):
                reply_path = store_path_for_agent(
                    data_dir, f"{data_dir}/inbox/{reply_to}/inbox.json", agent_cfg_entry,
                )
                msg_body += f"▶ 回复 {reply_to} → {reply_path}\n"

            forward_to = action_raw.get("forward_to", []) if action_raw else []
            if forward_to:
                targets = [t for t in forward_to if t != agent_name]
                if targets:
                    msg_body += f"\n▶ 需转发至: {', '.join(targets)}"

            msg_body += "\n---"
        from lib.application.orchestration.pipeline.task import pipeline_completion_block
        msg_body += pipeline_completion_block(
            data_dir, raw_content, agent_name, agent_cfg_entry,
        )
        combined_text += msg_body
    combined_text = _truncate_cli_text(combined_text, max_chars=combined_max)
    
    # 3. 多模型 fallback 推送
    # cli_cmd 如果是 list，按顺序试；如果是 str，当单条处理
    cli_commands = cli_cmd if isinstance(cli_cmd, list) else [cli_cmd]
    cli_commands = [c for c in cli_commands if c.strip()]
    
    if not cli_commands:
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []

    used_model = None
    agent_cfg_entry = agents_cfg.get(agent_name) or {}
    agent_types = cfg.get("agent_types") or {}
    msg_entries_pre = [
        m if isinstance(m, dict) else (m.to_dict() if hasattr(m, "to_dict") else m)
        for m in (messages or [])
    ]
    from lib.application.orchestration.pipeline.task import is_pipeline_execute_message

    pipeline_msg = any(
        is_pipeline_execute_message(e, data_dir) for e in msg_entries_pre
    )
    for cmd_template in cli_commands:
        from .agent_push import parse_model_from_push_template, try_build_push_direct

        model_name = parse_model_from_push_template(cmd_template)
        direct = try_build_push_direct(
            agent_name,
            agent_cfg_entry,
            agent_types,
            data_dir=data_dir,
            prompt=combined_text,
            model_name=model_name,
            pipeline=pipeline_msg,
        )
        cmd = "" if direct else _replace_msg_placeholder(cmd_template, combined_text)

        reply_dir = f"{data_dir}/replies" if data_dir else ""

        invoke_kw = dict(
            agent_name=agent_name,
            msg_ids=msg_ids,
            reply_dir=reply_dir,
            data_dir=data_dir,
            messages=messages,
        )
        success = _invoke_cli(cmd, direct=direct, **invoke_kw)
        if not success:
            for attempt in range(1, max_retries + 1):
                delay = 2 ** attempt + random.uniform(-1, 1)
                delay = max(0.5, min(delay, 30))
                time.sleep(delay)
                success = _invoke_cli(cmd, direct=direct, **invoke_kw)
                if success:
                    break

        if success:
            used_model = cmd_template
            break

    if used_model:
        agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents", {})
        agent_cfg = agents_cfg.get(agent_name, {})
        from lib.adapters.frameworks import should_mark_processing_on_push

        for mid in msg_ids:
            entry = next(
                (m for m in messages if (m.get("id") if isinstance(m, dict) else m.id) == mid),
                {},
            )
            entry_dict = entry if isinstance(entry, dict) else entry.to_dict()
            if auto_ack:
                from lib.scan import finalize_auto_ack
                finalize_auto_ack(data_dir, agent_name, mid, entry_dict)
            elif should_mark_processing_on_push(agent_cfg, entry_dict):
                from lib.scan import finalize_processing_on_push
                finalize_processing_on_push(data_dir, agent_name, mid, entry_dict)
            else:
                update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []

    for mid in msg_ids:
        if auto_ack:
            entry = next(
                (m for m in messages if (m.get("id") if isinstance(m, dict) else m.id) == mid),
                {},
            )
            from lib.scan import finalize_auto_ack
            finalize_auto_ack(data_dir, agent_name, mid, entry if isinstance(entry, dict) else entry.to_dict())
        else:
            update_message_status(data_dir, agent_name, mid, MsgStatus.FAILED)
            log_error(paths["errors"], mid, agent_name,
                      f"CLI 推送失败（{len(cli_commands)} 个模型均不可用）")
    
    return msg_ids


def resolve_cli(
    agent_cfg: dict,
    agent_types: dict,
    model_alias: str = None,
    agent_name: str = "",
    *,
    pipeline: bool = False,
    data_dir: str = "",
) -> str:
    """根据 agent 配置解析 push CLI（委托 agent_adapters 适配层）。"""
    from lib.adapters.frameworks import resolve_push_cli

    name = agent_name or agent_cfg.get("profile") or agent_cfg.get("agent") or ""
    return resolve_push_cli(
        name, agent_cfg, agent_types, model_alias, pipeline=pipeline, data_dir=data_dir,
    )


def resolve_cli_for_message(
    agent_cfg: dict,
    agent_types: dict,
    msg,
    agent_name: str,
    *,
    primary_task_id: str = "",
    data_dir: str = "",
) -> str:
    """按单条消息解析 CLI（含模型档位）。"""
    from .model_router import pick_model_alias, is_no_llm_notice

    if is_no_llm_notice(msg):
        return ""
    pipeline = False
    if data_dir:
        from lib.application.orchestration.pipeline.task import is_pipeline_execute_message
        entry = msg if isinstance(msg, dict) else (msg.to_dict() if hasattr(msg, "to_dict") else {})
        pipeline = is_pipeline_execute_message(entry, data_dir)
    cfg = {}
    if data_dir:
        cfg = json_read(os.path.join(data_dir, "config.json"), {})
    routing_out: dict = {}
    alias = pick_model_alias(
        msg,
        agent_name,
        agent_cfg,
        primary_task_id=primary_task_id,
        config=cfg or None,
        data_dir=data_dir,
        routing_out=routing_out,
    )
    action = msg.get("action", {}) if isinstance(msg, dict) else (getattr(msg, "action", None) or {})
    if isinstance(action, dict) and action.get("model_tier") == "flash":
        alias = "deepseek-flash"
    elif isinstance(action, dict) and action.get("model_tier") == "pro":
        from .model_router import TIER_PRO, _pro_allowed
        if _pro_allowed(agent_cfg):
            alias = TIER_PRO
        else:
            alias = "deepseek-flash"
    elif isinstance(action, dict) and action.get("model_tier") in ("ollama", "local"):
        from .model_router import TIER_OLLAMA
        alias = TIER_OLLAMA

    from .push_context import clear_push_context, set_push_context
    from .ollama_routing import resolve_ollama_settings

    set_push_context(data_dir=data_dir, config=cfg or None)
    if alias == "ollama-local" and cfg:
        settings = resolve_ollama_settings(cfg, data_dir)
        os.environ.setdefault("MAILBUS_OLLAMA_MODEL", settings["model"])
        os.environ.setdefault("MAILBUS_OLLAMA_BASE_URL", settings["base_url"])
    try:
        return resolve_cli(
            agent_cfg, agent_types, model_alias=alias, agent_name=agent_name,
            pipeline=pipeline, data_dir=data_dir,
        )
    finally:
        clear_push_context()


def resolve_cli_chain(agent_cfg: dict, agent_types: dict) -> list:
    """
    返回该 agent 的所有备用 CLI 命令列表（按 models 顺序）。

    支持多模型 fallback:
    1. 遍历 agent_cfg.models
    2. 每个别名生成一条 CLI 命令
    3. push_messages 按顺序试，成功就停

    返回: [(cli_cmd, model_alias), ...]
    """
    agent_models = agent_cfg.get("models", [])
    if not agent_models:
        cmd = resolve_cli(agent_cfg, agent_types)
        return [(cmd, None)]

    results = []
    for alias in agent_models:
        cmd = resolve_cli(agent_cfg, agent_types, model_alias=alias)
        if cmd:
            results.append((cmd, alias))
    return results


def _replace_msg_placeholder(cmd: str, text: str) -> str:
    """替换 CLI 模板中的 'MSG'，按 shell 类型转义引号。"""
    if "'MSG'" not in cmd:
        return cmd
    low = cmd.lower()
    if "powershell" in low:
        escaped = "'" + text.replace("'", "''") + "'"
    else:
        escaped = "'" + text.replace("'", "'\"'\"'") + "'"
    return cmd.replace("'MSG'", escaped)


def _invoke_cli(
    cmd: str,
    agent_name: str = "",
    msg_ids: list = None,
    reply_dir: str = "",
    data_dir: str = "",
    messages: list = None,
    *,
    direct: Optional[dict] = None,
) -> bool:
    """
    执行 CLI 命令将消息推送给 agent。
    
    参数 cmd 已替换好 'MSG' 占位符；direct 为 Windows claude 直连 argv（不经 shell）。
    从 .env 文件自动注入 API Key。
    将 agent 的回复 stdout 保存到 reply_dir/{agent_name}.json。
    返回 True 表示 CLI 启动成功（Popen 不阻塞）。
    """
    if not cmd and not direct:
        return True

    from .claude_launch import LAUNCH_QUEUE_PREFIX, enqueue_launch_queue

    if cmd.startswith(LAUNCH_QUEUE_PREFIX):
        inner = cmd[len(LAUNCH_QUEUE_PREFIX):]
        return enqueue_launch_queue(inner, agent_name or "push")

    try:
        push_argv = None if direct else _push_argv(cmd)
        # 获取需要注入的环境变量
        extra_env = get_env_for_cli(cmd) if cmd else {}
        
        # 确保子进程有完整的 shell 环境 + API Key
        env = os.environ.copy()
        env.update(extra_env)
        
        # 将 agent 的回复保存到文件
        reply_file = ""
        if reply_dir and agent_name:
            import json, time
            reply_file = f"{reply_dir}/{agent_name}.json"
        
        # 后台执行 CLI，不阻塞 scan，同时捕获回复
        if direct:
            direct_env = dict(env)
            direct_env.update(direct.get("env") or {})
            process = subprocess.Popen(
                direct["argv"],
                cwd=direct.get("cwd") or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=direct_env,
                close_fds=True,
                **_popen_no_window_kwargs(),
            )
        elif push_argv:
            process = subprocess.Popen(
                push_argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=env,
                close_fds=True,
                **_popen_no_window_kwargs(),
            )
        else:
            if sys.platform == "win32":
                return False
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=env,
                close_fds=True,
            )
        if agent_name:
            _register_cli_proc(agent_name, process)

        # 异步读取回复并保存
        if reply_file and agent_name:
            msg_entries = [
                m if isinstance(m, dict) else (m.to_dict() if hasattr(m, "to_dict") else m)
                for m in (messages or [])
            ]
            from lib.application.orchestration.pipeline.task import is_pipeline_execute_message
            from lib.adapters.frameworks import push_timeout_for

            agents_cfg_pre = json_read(os.path.join(data_dir, "config.json"), {}).get("agents", {})
            agent_cfg_pre = agents_cfg_pre.get(agent_name, {})
            pipeline_msg = any(
                is_pipeline_execute_message(e, data_dir) for e in msg_entries
            )
            cli_timeout = push_timeout_for(agent_cfg_pre, pipeline=pipeline_msg)

            def _save_reply(proc, fpath, a_name, mids, dd, entries, timeout):
                try:
                    stdout, _ = proc.communicate(timeout=timeout)
                    if isinstance(stdout, bytes):
                        reply_text = stdout.decode("utf-8", errors="replace").strip()
                    else:
                        reply_text = (stdout or "").strip()
                    if reply_text and len(reply_text) > 5:
                        from datetime import datetime, timezone, timedelta
                        ts = now_dt().strftime("%Y-%m-%dT%H:%M:%S+0800")
                        reply_data = {
                            "agent": a_name,
                            "msg_ids": mids or [],
                            "reply": reply_text[:16000],
                            "timestamp": ts,
                        }
                        os.makedirs(os.path.dirname(fpath), exist_ok=True)
                        json_write(fpath, reply_data)
                    # pipeline 落盘验收（CLI 结束后，拒绝 phantom completion）
                    import time
                    time.sleep(2)
                    from .self_heal import agent_cli_active_for
                    from lib.application.orchestration.pipeline.task import (
                        extract_task_id,
                        is_pipeline_execute_message,
                        verify_pipeline_step_delivery,
                    )
                    from lib.scan import update_message_status
                    from .models import MsgStatus
                    from .utils import json_read as _json_read

                    agents_cfg = _json_read(os.path.join(dd, "config.json"), {}).get("agents", {})
                    agent_cfg_entry = agents_cfg.get(a_name) or {}
                    agent_type = agent_cfg_entry.get("type", "")

                    for entry in entries or []:
                        from .file_task_push import should_file_task_push, verify_file_task_delivery
                        from lib.application.orchestration.pipeline.task import is_pipeline_execute_message

                        is_pipe = is_pipeline_execute_message(entry, dd)
                        raw = entry.get("content", "") if isinstance(entry, dict) else ""
                        is_file = should_file_task_push(agent_type, agent_cfg_entry, entry, raw) and not is_pipe
                        if not is_pipe and not is_file:
                            continue
                        reply_phantom = False
                        if reply_text:
                            from .phantom_detect import is_phantom_reply_text
                            reply_phantom = is_phantom_reply_text(reply_text)
                        if is_file:
                            ok, reason = verify_file_task_delivery(
                                dd, a_name, entry, reply_text=reply_text,
                            )
                        else:
                            ok, reason = verify_pipeline_step_delivery(dd, a_name, entry)
                        if reply_phantom and ok:
                            ok, reason = False, "phantom_reply_text"
                        stall_reason = None
                        if reply_text:
                            from .api_stall_detect import detect_api_stall
                            stall_reason = detect_api_stall(reply_text)
                        if stall_reason and not ok:
                            from .api_stall_recovery import schedule_api_stall_recovery
                            from lib.application.orchestration.pipeline.task import extract_task_id as _extract_tid

                            mid = entry.get("id") if isinstance(entry, dict) else ""
                            tid = (
                                entry.get("task_id") if isinstance(entry, dict) else ""
                            ) or _extract_tid(raw)
                            if not agent_cli_active_for(
                                a_name, agents_cfg, msg_id=mid, task_id=tid,
                            ):
                                schedule_api_stall_recovery(
                                    dd, a_name, mid,
                                    reason=stall_reason,
                                    task_id=tid,
                                    reply_excerpt=reply_text,
                                )
                                continue
                        if ok:
                            continue
                        mid = entry.get("id") if isinstance(entry, dict) else ""
                        if agent_cli_active_for(
                            a_name,
                            agents_cfg,
                            msg_id=mid,
                            task_id=entry.get("task_id") if isinstance(entry, dict) else ""
                            or extract_task_id(raw),
                        ):
                            debug(
                                f"[pusher] pipeline-delivery {a_name} msg={mid}: "
                                f"{reason} — CLI active, skip reset"
                            )
                            continue
                        warn(
                            f"[pusher] pipeline-delivery {a_name} msg={mid}: "
                            f"{reason} — reset pending"
                        )
                        tid = (
                            entry.get("task_id") if isinstance(entry, dict) else ""
                        ) or extract_task_id(raw)
                        if is_pipe and tid:
                            from lib.application.orchestration.dispatch.pipeline_step_failover import note_pipeline_verify_failure
                            note_pipeline_verify_failure(
                                dd, tid, a_name, mid, reason=reason,
                            )
                        update_message_status(dd, a_name, mid, MsgStatus.PENDING)
                except subprocess.TimeoutExpired:
                    _kill_cli_proc(proc, a_name)
                    from .models import MsgStatus
                    from lib.scan import update_message_status
                    from .file_task_push import is_executable_task
                    partial = ""
                    try:
                        out, _ = proc.communicate(timeout=5)
                        if isinstance(out, bytes):
                            partial = out.decode("utf-8", errors="replace").strip()
                        else:
                            partial = (out or "").strip()
                    except Exception:
                        pass
                    timeout_note = f"[mailbus] CLI timeout after {timeout}s"
                    if partial:
                        timeout_note = f"{timeout_note}\n{partial[:1500]}"
                    if fpath:
                        from datetime import datetime, timezone, timedelta
                        ts = now_dt().strftime(
                            "%Y-%m-%dT%H:%M:%S+0800"
                        )
                        os.makedirs(os.path.dirname(fpath), exist_ok=True)
                        json_write(fpath, {
                            "agent": a_name,
                            "msg_ids": mids or [],
                            "reply": timeout_note[:16000],
                            "timestamp": ts,
                            "error": "timeout",
                        })
                    for entry in entries or []:
                        if not is_executable_task(entry if isinstance(entry, dict) else {}):
                            continue
                        mid = entry.get("id") if isinstance(entry, dict) else ""
                        if mid:
                            warn(f"[pusher] CLI timeout {a_name} msg={mid} — killed proc, reset pending")
                            update_message_status(dd, a_name, mid, MsgStatus.PENDING)
                except Exception as exc:
                    warn(f"[pusher] _save_reply failed {a_name}: {type(exc).__name__}: {exc}")
                finally:
                    if a_name:
                        _ACTIVE_CLI_PROCS.pop(a_name, None)
            import threading
            t = threading.Thread(
                target=_save_reply,
                args=(process, reply_file, agent_name, msg_ids, data_dir, msg_entries, cli_timeout),
                daemon=True,
            )
            t.start()
        
        return True
    except Exception as e:
        warn(f"[pusher] CLI background start failed: {e}")
        return False


def _wait_for_ack(data_dir: str, agent_name: str, msg_ids: list, timeout: int) -> bool:
    """
    等待 agent 通过 ack_handler 确认收到。
    
    轮询 agent 的 ack.json 文件。
    返回 True 表示所有消息都已 ack。
    """
    paths = resolve_paths(data_dir)
    ack_file = f"{paths['inbox']}/{agent_name}/ack.json"
    
    deadline = now_ts() + timeout
    acked_ids = set()
    
    while now_ts() < deadline:
        ack_data = json_read(ack_file, [])
        if isinstance(ack_data, dict):
            ack_data = [ack_data]  # 兼容单对象格式
        
        for ack in ack_data:
            if isinstance(ack, dict) and ack.get("action") == "ack":
                acked_ids.add(ack.get("msg_id"))
        
        if all(mid in acked_ids for mid in msg_ids):
            return True
        
        time.sleep(1)
    
    return False


def _get_unacked_ids(data_dir: str, agent_name: str, msg_ids: list) -> list:
    """获取尚未 ack 的消息 ID 列表（委托 ResultStore ack 适配器）。"""
    from lib.adapters.results.ack import list_unacked

    return list_unacked(data_dir, agent_name, msg_ids)


def _update_status_direct(data_dir: str, agent_name: str, msg_id: str, status: str):
    """直接通过 scanner 更新状态"""
    from lib.scan import update_message_status
    update_message_status(data_dir, agent_name, msg_id, status)
