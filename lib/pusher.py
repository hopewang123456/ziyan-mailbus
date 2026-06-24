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

from .models import Message, MsgStatus, Priority, MsgType
from .constants import DEFAULT_CLI_MSG_MAX_CHARS
from .utils import json_read, json_write, jsonl_append, log_error, resolve_paths, _now_iso
from .scanner import mark_as_pushed, update_message_status
from .mbus_log import debug, warn

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

    # 搜索路径：先找项目根，再找 ~/.hermes/.env
    bus_dir = Path(__file__).resolve().parent.parent  # mailbus/lib/ → mailbus/
    candidates = [
        bus_dir / ".env",
        Path("/run/hermes/.env"),
        Path("/home/hermes/.hermes/.env"),
        Path("/home/administrator/.hermes/.env"),
        Path("/mnt/e/hermes-data/.hermes/.env"),
        Path.home() / ".hermes" / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            with open(env_path) as f:
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
    paths = resolve_paths(data_dir)
    
    # 0. 幂等去重：检查这些消息是否已经被 agent ack 过
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if inbox_data:
        from .scanner import _get_acked_ids
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
    # ── P1/A: 精简推送 + 规则文档外置 ──
    # 系统上下文精简为7行核心信息，不再嵌入长说明
    # 规则文档路径引用由 store/rules/ 外部文件提供
    rules_dir = f"{data_dir}/rules"
    system_context = (
        f"mailbus | agent={agent_name}\n"
        f"inbox={data_dir}/inbox/{agent_name}/inbox.json\n"
        f"ack={data_dir}/inbox/{agent_name}/ack.json\n"
        f"rules={rules_dir}/\n---\n"
    )
    combined_text = system_context

    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents_cfg = cfg.get("agents", {})
    from .token_budget import load_token_budget
    tb = load_token_budget(cfg)
    per_msg_max = int(
        (agents_cfg.get(agent_name) or {}).get("cli_msg_max_chars")
        or tb.get("cli_msg_max_chars")
        or DEFAULT_CLI_MSG_MAX_CHARS
    )
    combined_max = int(tb.get("cli_combined_max_chars") or 4000)

    for msg_entry in messages:
        from_ = msg_entry.get("from", "?") if isinstance(msg_entry, dict) else msg_entry.from_
        content = msg_entry.get("content", "") if isinstance(msg_entry, dict) else msg_entry.content
        raw_content = content or ""
        content = _truncate_cli_text(raw_content, max_chars=per_msg_max)
        msg_id = msg_entry.get("id", "") if isinstance(msg_entry, dict) else msg_entry.id
        action_raw = msg_entry.get("action", {}) if isinstance(msg_entry, dict) else (msg_entry.action or MsgType.default_action(msg_entry.type))
        msg_type = msg_entry.get("type", "notice") if isinstance(msg_entry, dict) else msg_entry.type
        fwd_chain = msg_entry.get("forward_chain") if isinstance(msg_entry, dict) else msg_entry.forward_chain

        entry_dict = msg_entry if isinstance(msg_entry, dict) else msg_entry.to_dict()
        agent_cfg_entry = agents_cfg.get(agent_name) or {}
        agent_type = agent_cfg_entry.get("type", "")
        from .file_task_push import (
            build_file_task_push_body,
            ensure_file_task_work_order,
            should_file_task_push,
        )
        if should_file_task_push(agent_type, agent_cfg_entry, entry_dict, raw_content):
            _, wo_path, rf_path = ensure_file_task_work_order(data_dir, agent_name, entry_dict)
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
                reply_path = f"{data_dir}/inbox/{reply_to}/inbox.json"
                msg_body += f"▶ 回复 {reply_to} → {reply_path}\n"

            forward_to = action_raw.get("forward_to", []) if action_raw else []
            if forward_to:
                targets = [t for t in forward_to if t != agent_name]
                if targets:
                    msg_body += f"\n▶ 需转发至: {', '.join(targets)}"

            msg_body += "\n---"
        from .pipeline_task import pipeline_completion_block
        msg_body += pipeline_completion_block(data_dir, raw_content, agent_name)
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
    for cmd_template in cli_commands:
        cmd = cmd_template.replace("'MSG'", f"'{combined_text}'")
        
        reply_dir = f"{data_dir}/replies" if data_dir else ""
        
        success = _invoke_cli(cmd, agent_name=agent_name, msg_ids=msg_ids, reply_dir=reply_dir, data_dir=data_dir, messages=messages)
        if not success:
            for attempt in range(1, max_retries + 1):
                # 指数退避 + jitter: base 2s, 乘 2^attempt, 加 ±1s 抖动
                delay = 2 ** attempt + random.uniform(-1, 1)
                delay = max(0.5, min(delay, 30))  # 钳制在 [0.5, 30] 秒
                time.sleep(delay)
                success = _invoke_cli(cmd, agent_name=agent_name, msg_ids=msg_ids, reply_dir=reply_dir, data_dir=data_dir, messages=messages)
                if success:
                    break
        
        if success:
            used_model = cmd_template
            break
    
    if used_model:
        agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents", {})
        agent_cfg = agents_cfg.get(agent_name, {})
        from .agent_adapters import should_mark_processing_on_push

        for mid in msg_ids:
            entry = next(
                (m for m in messages if (m.get("id") if isinstance(m, dict) else m.id) == mid),
                {},
            )
            entry_dict = entry if isinstance(entry, dict) else entry.to_dict()
            if auto_ack:
                from .scanner import finalize_auto_ack
                finalize_auto_ack(data_dir, agent_name, mid, entry_dict)
            elif should_mark_processing_on_push(agent_cfg, entry_dict):
                from .scanner import finalize_processing_on_push
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
            from .scanner import finalize_auto_ack
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
) -> str:
    """根据 agent 配置解析 push CLI（委托 agent_adapters 适配层）。"""
    from .agent_adapters import resolve_push_cli

    name = agent_name or agent_cfg.get("profile") or agent_cfg.get("agent") or ""
    return resolve_push_cli(name, agent_cfg, agent_types, model_alias)


def resolve_cli_for_message(
    agent_cfg: dict,
    agent_types: dict,
    msg,
    agent_name: str,
    *,
    primary_task_id: str = "",
) -> str:
    """按单条消息解析 CLI（含模型档位）。"""
    from .model_router import pick_model_alias, is_no_llm_notice

    if is_no_llm_notice(msg):
        return ""
    alias = pick_model_alias(msg, agent_name, agent_cfg, primary_task_id=primary_task_id)
    action = msg.get("action", {}) if isinstance(msg, dict) else (getattr(msg, "action", None) or {})
    if isinstance(action, dict) and action.get("model_tier") == "flash":
        alias = "deepseek-flash"
    elif isinstance(action, dict) and action.get("model_tier") == "pro":
        from .model_router import TIER_PRO, _pro_allowed
        if _pro_allowed(agent_cfg):
            alias = TIER_PRO
        else:
            alias = "deepseek-flash"
    return resolve_cli(agent_cfg, agent_types, model_alias=alias, agent_name=agent_name)


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


def _invoke_cli(cmd: str, agent_name: str = "", msg_ids: list = None, reply_dir: str = "", data_dir: str = "", messages: list = None) -> bool:
    """
    执行 CLI 命令将消息推送给 agent。
    
    参数 cmd 已替换好 'MSG' 占位符。
    从 .env 文件自动注入 API Key。
    将 agent 的回复 stdout 保存到 reply_dir/{agent_name}.json。
    返回 True 表示 CLI 启动成功（Popen 不阻塞）。
    """
    if not cmd:
        return True
    
    try:
        # 获取需要注入的环境变量
        extra_env = get_env_for_cli(cmd)
        
        # 确保子进程有完整的 shell 环境 + API Key
        env = os.environ.copy()
        env.update(extra_env)
        
        # 将 agent 的回复保存到文件
        reply_file = ""
        if reply_dir and agent_name:
            import json, time
            reply_file = f"{reply_dir}/{agent_name}.json"
        
        # 后台执行 CLI，不阻塞 scan，同时捕获回复
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
            close_fds=True,
        )
        
        # 异步读取回复并保存
        if reply_file and agent_name:
            msg_entries = [
                m if isinstance(m, dict) else (m.to_dict() if hasattr(m, "to_dict") else m)
                for m in (messages or [])
            ]
            from .pipeline_task import is_pipeline_execute_message
            from .agent_adapters import push_timeout_for

            agents_cfg_pre = json_read(os.path.join(data_dir, "config.json"), {}).get("agents", {})
            agent_cfg_pre = agents_cfg_pre.get(agent_name, {})
            pipeline_msg = any(
                is_pipeline_execute_message(e, data_dir) for e in msg_entries
            )
            cli_timeout = push_timeout_for(agent_cfg_pre, pipeline=pipeline_msg)

            def _save_reply(proc, fpath, a_name, mids, dd, entries, timeout):
                try:
                    stdout, _ = proc.communicate(timeout=timeout)
                    reply_text = stdout.decode("utf-8", errors="replace").strip()
                    if reply_text and len(reply_text) > 5:
                        from datetime import datetime, timezone, timedelta
                        ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+0800")
                        reply_data = {
                            "agent": a_name,
                            "msg_ids": mids or [],
                            "reply": reply_text[:2000],
                            "timestamp": ts,
                        }
                        import json
                        os.makedirs(os.path.dirname(fpath), exist_ok=True)
                        with open(fpath, "w") as f:
                            json.dump(reply_data, f, ensure_ascii=False, indent=2)
                    # pipeline 落盘验收（CLI 结束后，拒绝 phantom completion）
                    import time
                    time.sleep(2)
                    from .self_heal import agent_cli_active
                    from .pipeline_task import (
                        is_pipeline_execute_message,
                        verify_pipeline_step_delivery,
                    )
                    from .scanner import update_message_status
                    from .models import MsgStatus
                    from .utils import json_read as _json_read

                    agents_cfg = _json_read(os.path.join(dd, "config.json"), {}).get("agents", {})
                    agent_cfg_entry = agents_cfg.get(a_name) or {}
                    agent_type = agent_cfg_entry.get("type", "")

                    for entry in entries or []:
                        from .file_task_push import should_file_task_push, verify_file_task_delivery
                        from .pipeline_task import is_pipeline_execute_message

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
                        if ok:
                            continue
                        mid = entry.get("id") if isinstance(entry, dict) else ""
                        if agent_cli_active(a_name, agents_cfg):
                            debug(
                                f"[pusher] pipeline-delivery {a_name} msg={mid}: "
                                f"{reason} — CLI active, skip reset"
                            )
                            continue
                        warn(
                            f"[pusher] pipeline-delivery {a_name} msg={mid}: "
                            f"{reason} — reset pending"
                        )
                        update_message_status(dd, a_name, mid, MsgStatus.PENDING)
                except subprocess.TimeoutExpired:
                    from .models import MsgStatus
                    from .scanner import update_message_status
                    from .file_task_push import is_executable_task
                    from .utils import json_read as _json_read
                    for entry in entries or []:
                        if not is_executable_task(entry if isinstance(entry, dict) else {}):
                            continue
                        mid = entry.get("id") if isinstance(entry, dict) else ""
                        if mid:
                            warn(f"[pusher] CLI timeout {a_name} msg={mid} — reset pending")
                            update_message_status(dd, a_name, mid, MsgStatus.PENDING)
                except Exception:
                    pass
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
    
    deadline = time.time() + timeout
    acked_ids = set()
    
    while time.time() < deadline:
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
    """获取尚未 ack 的消息 ID 列表"""
    paths = resolve_paths(data_dir)
    ack_file = f"{paths['inbox']}/{agent_name}/ack.json"
    
    ack_data = json_read(ack_file, [])
    if isinstance(ack_data, dict):
        ack_data = [ack_data]
    
    acked_ids = {a.get("msg_id") for a in ack_data if isinstance(a, dict) and a.get("action") == "ack"}
    return [mid for mid in msg_ids if mid not in acked_ids]


def _update_status_direct(data_dir: str, agent_name: str, msg_id: str, status: str):
    """直接通过 scanner 更新状态"""
    from .scanner import update_message_status
    update_message_status(data_dir, agent_name, msg_id, status)
