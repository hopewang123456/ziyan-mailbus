"""
ziyan-mailbus pusher

从队列读取待推送消息，通过 CLI 推送给 agent，等待 ack。
"""

import os
import subprocess
import time
from typing import Optional
from pathlib import Path

from .models import Message, MsgStatus, Priority
from .utils import json_read, json_write, jsonl_append, log_error, resolve_paths, _now_iso
from .scanner import mark_as_pushed, update_message_status

# ── API Key 注入 ─────────────────────────────────────────────────────
# 从 bus.py 所在目录的上级搜索 .env 文件
_ENV_LOADED = False
_ENV_VARS = {}


def _load_env():
    """加载 mailbus 项目目录下的 .env 文件，缓存到全局变量"""
    global _ENV_LOADED, _ENV_VARS
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    # 搜索路径：先找项目根，再找 ~/.hermes/.env
    bus_dir = Path(__file__).resolve().parent.parent  # mailbus/lib/ → mailbus/
    candidates = [
        bus_dir / ".env",
        Path("/home/administrator/.hermes/.env"),
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
                    _ENV_VARS[key] = val
            break  # 找到第一个有效的 .env 就停


def get_env_for_cli(cmd: str) -> dict:
    """给 CLI 命令补充环境变量"""
    _load_env()
    # 只注入 CLI 命令相关的 API Key
    # 通过 cmd 中提到的 provider 名推断
    extra_env = {}
    if "deepseek" in cmd.lower() or "openai-compatible" in cmd.lower():
        if "DEEPSEEK_API_KEY" in _ENV_VARS:
            extra_env["DEEPSEEK_API_KEY"] = _ENV_VARS["DEEPSEEK_API_KEY"]
    if "openrouter" in cmd.lower():
        if "OPENROUTER_API_KEY" in _ENV_VARS:
            extra_env["OPENROUTER_API_KEY"] = _ENV_VARS["OPENROUTER_API_KEY"]
    if "anthropic" in cmd.lower() or "claude" in cmd.lower():
        if "ANTHROPIC_API_KEY" in _ENV_VARS:
            extra_env["ANTHROPIC_API_KEY"] = _ENV_VARS["ANTHROPIC_API_KEY"]
    if "openai" in cmd.lower():
        if "OPENAI_API_KEY" in _ENV_VARS:
            extra_env["OPENAI_API_KEY"] = _ENV_VARS["OPENAI_API_KEY"]
    return extra_env


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
    msg_ids = [m.id if hasattr(m, 'id') else m["id"] for m in messages]
    paths = resolve_paths(data_dir)
    
    # 0. 幂等去重：检查这些消息是否已经被 agent ack 过
    # 如果已经被 ack，直接返回空（不需要再推）
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if inbox_data:
        from .scanner import _get_acked_ids
        acked_ids = _get_acked_ids(inbox_data)
        already_acked = [mid for mid in msg_ids if mid in acked_ids]
        if already_acked:
            # 已 ack 的消息直接标记为 acknowledged（不用再推）
            for mid in already_acked:
                update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
            # 过滤掉已 ack 的，只推未处理的
            remaining = [mid for mid in msg_ids if mid not in acked_ids]
            if not remaining:
                return []
            msg_ids = remaining
            # 从 messages 中也过滤掉
            messages = [m for m in messages if (m.id if hasattr(m, 'id') else m["id"]) in msg_ids]
    
    # 1. 标记为 pushed
    mark_as_pushed(data_dir, agent_name, msg_ids)
    
    # 如果没有 CLI 配置，走纯文件通信 — 标记为 pushed，等待 agent 自检后写 ack
    if not cli_cmd:
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []
    
    # 2. 构建推送文本（从 Message.action 结构化字段读取指令）
    text_parts = []
    for m in messages:
        # 兼容 dict 和 Message 对象
        if isinstance(m, dict):
            from_ = m.get("from", "?")
            content = m.get("content", "")
            msg_id = m.get("id", "")
            action = m.get("action", {})
            msg_type = m.get("type", "notice")
            task_data = m.get("task")
            fwd_chain = m.get("forward_chain")
        else:
            from_ = m.from_
            content = m.content
            msg_id = m.id
            action = m.action or MsgType.default_action(m.type)
            msg_type = m.type
            task_data = m.task
            fwd_chain = m.forward_chain

        # ack 路径（从 data_dir 推导，确保迁移时路径正确）
        ack_path = f"{data_dir}/inbox/{agent_name}/ack.json"

        # 构建指令列表
        instructions = []
        # 1. ack（总是有）
        instructions.append(f"""【必须】写 ack 确认已读
  文件: {ack_path}
  格式: {{"action":"ack","msg_id":"{msg_id}","agent":"{agent_name}","timestamp":"<当前ISO时间>"}}""")

        # 2. 回复发件人
        reply_to = action.get("reply_to", "") if action else ""
        if reply_to and reply_to not in ("mailbus", "broadcast", "system", "manual", "mailbus-test", "test", ""):
            reply_path = f"{data_dir}/inbox/{reply_to}/inbox.json"
            reply_msg_id = f"reply-{msg_id}"
            instructions.append(f"""【必须】回复发件人 {reply_to}
  文件: {reply_path}
  向 messages 数组追加一条新消息，设 has_unread: true，格式:
  {{"id": "{reply_msg_id}", "from": "{agent_name}", "to": "{reply_to}", "priority": "normal", "type": "reply", "content": "<你的回复>", "status": "pending", "created_at": "<当前ISO时间>"}}""")

        # 3. 转发
        forward_to = action.get("forward_to", []) if action else []
        if forward_to:
            fwd_lines = []
            for target in forward_to:
                if target == agent_name:
                    continue
                fwd_path = f"{data_dir}/inbox/{target}/inbox.json"
                fwd_msg_id = f"fwd-{msg_id}-{target}"
                fwd_lines.append(f"""  目标: {target}
  文件: {fwd_path}
  格式: {{"id": "{fwd_msg_id}", "from": "{agent_name}", "to": "{target}", "priority": "normal", "type": "forward", "content": "<你的说明>", "status": "pending", "created_at": "<当前ISO时间>"}}""")
            instructions.append(f"""【必须】转发给指定 agent
  转发至: {', '.join(forward_to)}
{'---'.join(fwd_lines)}""")

            if reply_to:
                instructions.append(f"【注意】转发完成后，请回复发件人 {reply_to} 告知已转发。")

        # 4. 执行任务
        execute = action.get("execute", False) if action else False
        if execute:
            task_summary = ""
            if task_data:
                task_summary = task_data.get("summary", "")
            exec_text = f"""【必须】执行任务
  消息内容即为任务描述。请直接执行。"""
            if task_summary:
                exec_text += f"\n  任务概要: {task_summary}"
            if task_data and task_data.get("deliverable"):
                exec_text += f"\n  交付物: {task_data['deliverable']}"
            instructions.append(exec_text)

        # 5. 存记忆
        store_memory = action.get("store_memory", True) if action else True
        if store_memory:
            instructions.append("""【建议】存入本地记忆
  处理完消息后，将关键信息存入你的记忆系统，方便以后检索。""")

        # 6. 追踪链
        chain_text = ""
        if fwd_chain and fwd_chain.get("hops"):
            hops = fwd_chain["hops"]
            chain_text = "\n".join([f"  {h.get('agent','?')}: {h.get('action','?')}" for h in hops])
            chain_text = f"\n━━━━ 消息追踪链 ━━━━\n{chain_text}\n【你需在回复后更新此链】"

        text_parts.append(f"""╔══════════════════════════════════════════╗
║        ziyan-mailbus 消息总线           ║
╚══════════════════════════════════════════╝

📬 你有一条新消息

━━━━ 消息内容 ━━━━
类型: {msg_type}
来自: {from_}
内容: {content}
消息ID: {msg_id}{chain_text}

━━━━ 请执行以下操作 ━━━━
{chr(10).join(instructions)}
━━━━━━━━━━━━━━━━""")
    combined_text = "\n---\n".join(text_parts)
    
    # 在第一条消息前加上 mailbus 系统上下文（仅首次）
    system_context = f"""【系统上下文】你正在通过 ziyan-mailbus 消息总线工作。

你的名称: {agent_name}
你的 inbox: {data_dir}/inbox/{agent_name}/inbox.json
你的 ack 路径: {data_dir}/inbox/{agent_name}/ack.json

mailbus 通过 CLI 将消息推送给你。你收到的每条消息都包含操作指令，
请按【必须】标记的步骤执行，最重要的是写 ack 确认已读。

---
"""
    combined_text = system_context + combined_text
    
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
        
        success = _invoke_cli(cmd)
        if not success:
            for attempt in range(1, max_retries + 1):
                time.sleep(3)
                success = _invoke_cli(cmd)
                if success:
                    break
        
        if success:
            used_model = cmd_template
            break
    
    if used_model:
        for mid in msg_ids:
            if auto_ack:
                update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
            else:
                update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []

    for mid in msg_ids:
        if auto_ack:
            update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
        else:
            update_message_status(data_dir, agent_name, mid, MsgStatus.FAILED)
            log_error(paths["errors"], mid, agent_name,
                      f"CLI 推送失败（{len(cli_commands)} 个模型均不可用）")
    
    return msg_ids


def resolve_cli(agent_cfg: dict, agent_types: dict, model_alias: str = None) -> str:
    """
    根据 agent 配置、类型和模型别名，解析最终的 CLI 命令。

    参数:
        agent_cfg: agent 配置（含 type, profile, agent 等字段）
        agent_types: agent 类型模板字典
        model_alias: 使用的模型别名。为 None 时尝试从 agent_cfg.models 取第一个

    返回:
        CLI 命令字符串（'MSG' 占位符替换由调用方负责）
    """
    atype = agent_cfg.get("type", "none")
    tmpl = agent_types.get(atype, {}).get("push", "")
    if not tmpl:
        return ""

    # 1. 先替换基础占位符
    cmd = tmpl
    cmd = cmd.replace("PROFILE", agent_cfg.get("profile", ""))
    cmd = cmd.replace("AGENT", agent_cfg.get("agent", ""))

    # 2. 解析模型参数
    models_map = agent_types.get("models", {})
    if not model_alias:
        agent_models = agent_cfg.get("models", [])
        model_alias = agent_models[0] if agent_models else None

    model_flag = ""
    if model_alias and model_alias in models_map:
        model_flag = models_map[model_alias].get(atype, "")

    # 3. 替换 MODEL 占位符
    if model_flag:
        cmd = cmd.replace("MODEL", model_flag)
        cmd = cmd.replace("--model MODEL", model_flag)
        cmd = cmd.replace("-m MODEL", model_flag)
    else:
        cmd = cmd.replace("--model MODEL", "").replace("-m MODEL", "")
        cmd = cmd.replace("'MODEL'", "").replace("MODEL", "")

    # 4. 替换 PROVIDER 占位符
    provider = agent_cfg.get("provider", "")
    if not provider and model_alias and model_alias in models_map:
        provider = models_map[model_alias].get(atype, "")
    if provider:
        cmd = cmd.replace("PROVIDER", provider)
        cmd = cmd.replace("--provider PROVIDER", provider)
    else:
        cmd = cmd.replace("--provider PROVIDER", "").replace("PROVIDER", "")

    return cmd.strip()


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


def _invoke_cli(cmd: str) -> bool:
    """
    执行 CLI 命令将消息推送给 agent。
    
    参数 cmd 已替换好 'MSG' 占位符。
    从 .env 文件自动注入 API Key。
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
        
        # 后台执行 CLI，不阻塞 scan
        # start_new_session=True + preexec_fn 确保独立进程组
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
            close_fds=True,
        )
        # 不等待完成，直接返回成功（消息已投递）
        return True
    except Exception as e:
        print(f"[pusher] CLI 后台启动失败: {e}", file=sys.stderr)
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
