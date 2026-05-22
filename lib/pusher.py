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
    cli_cmd: str,
    ack_timeout: int = 30,
    max_retries: int = 3,
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
    
    返回:
        推送失败的消息 ID 列表（推送成功即视为送达，不等待 ack）
    """
    failed_ids = []
    msg_ids = [m.id if hasattr(m, 'id') else m["id"] for m in messages]
    paths = resolve_paths(data_dir)
    
    # 1. 标记为 pushed
    mark_as_pushed(data_dir, agent_name, msg_ids)
    
    # 如果没有 CLI 配置，走纯文件通信 — 标记为 pushed，等待 agent 自检后写 ack
    if not cli_cmd:
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []
    
    # 2. 构建推送文本（包含明确的操作指令）
    text_parts = []
    for m in messages:
        from_ = m.from_ if hasattr(m, 'from_') else m.get("from", "?")
        content = m.content if hasattr(m, 'content') else m.get("content", "")
        msg_id = m.id if hasattr(m, 'id') else m["id"]
        
        # ack 路径
        ack_path = f"/mnt/e/ai_tools/mail/store/inbox/{agent_name}/ack.json"
        
        text_parts.append(f"""📬 你有一条新消息

━━━━ 消息内容 ━━━━
来自: {from_}
内容: {content}
消息ID: {msg_id}

━━━━ 请执行以下操作 ━━━━
【必须】写 ack 确认已读
  文件: {ack_path}
  格式: {{"action":"ack","msg_id":"{msg_id}","agent":"{agent_name}","timestamp":"<当前ISO时间>"}}

【根据消息内容决定】
- 如果需要转发给其他 agent，直接写目标 inbox:
  /mnt/e/ai_tools/mail/store/inbox/<目标agent名>/inbox.json
  (追加到 messages 数组，设 has_unread: true)

- 如果需要存储到记忆或执行任务，按消息内容处理
━━━━━━━━━━━━━━━━""")
    combined_text = "\n---\n".join(text_parts)
    
    # 3. 替换 'MSG' 占位符
    cmd = cli_cmd.replace("'MSG'", f"'{combined_text}'")
    
    # 4. CLI 推送
    success = _invoke_cli(cmd)
    
    if success:
        # 推送成功 → 标记为 pushed（等待 agent 写 ack 确认）
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
        return []
    
    # 5. 首次失败 → 重试
    for attempt in range(1, max_retries + 1):
        time.sleep(5)
        success = _invoke_cli(cmd)
        if success:
            for mid in msg_ids:
                update_message_status(data_dir, agent_name, mid, MsgStatus.PUSHED)
            return []
    
    # 6. 全部失败 → 写错误日志
    for mid in msg_ids:
        update_message_status(data_dir, agent_name, mid, MsgStatus.FAILED)
        log_error(paths["errors"], mid, agent_name,
                  f"CLI 推送失败（{max_retries} 次重试均失败）")
    
    return msg_ids


def resolve_cli(agent_cfg: dict, agent_types: dict) -> str:
    """根据 agent 配置和类型，解析最终的 CLI 命令"""
    atype = agent_cfg.get("type", "none")
    tmpl = agent_types.get(atype, {}).get("push", "")
    if not tmpl:
        return ""
    cmd = tmpl
    cmd = cmd.replace("PROFILE", agent_cfg.get("profile", ""))
    cmd = cmd.replace("AGENT", agent_cfg.get("agent", ""))
    return cmd


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
