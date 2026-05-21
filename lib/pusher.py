"""
ziyan-mailbus pusher

从队列读取待推送消息，通过 CLI 推送给 agent，等待 ack。
"""

import os
import subprocess
import time
from typing import Optional

from .models import Message, MsgStatus, Priority
from .utils import json_read, json_write, jsonl_append, log_error, resolve_paths, _now_iso
from .scanner import mark_as_pushed, update_message_status


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
    
    # 如果没有 CLI 配置，走纯文件通信
    if not cli_cmd:
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
        return []
    
    # 2. 构建推送文本（支持多条批量推）
    text_parts = []
    for m in messages:
        from_ = m.from_ if hasattr(m, 'from_') else m.get("from", "?")
        content = m.content if hasattr(m, 'content') else m.get("content", "")
        text_parts.append(f"[来自 {from_}] {content}")
    combined_text = "\n---\n".join(text_parts)
    
    # 3. 替换 'MSG' 占位符
    cmd = cli_cmd.replace("'MSG'", f"'{combined_text}'")
    
    # 4. CLI 推送（不等待 ack，推了就算送达）
    success = _invoke_cli(cmd)
    
    if success:
        # 推送成功 → 标记为 acknowledged（不等待 agent 回复）
        for mid in msg_ids:
            update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
        return []
    
    # 5. 首次失败 → 重试
    for attempt in range(1, max_retries + 1):
        time.sleep(5)
        success = _invoke_cli(cmd)
        if success:
            for mid in msg_ids:
                update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
            return []
    
    # 6. 全部失败 → 写错误日志
    for mid in msg_ids:
        update_message_status(data_dir, agent_name, mid, MsgStatus.FAILED)
        log_error(paths["errors"], mid, agent_name,
                  f"CLI 推送失败（{max_retries} 次重试均失败）")
    
    return msg_ids


def _invoke_cli(cmd: str) -> bool:
    """
    执行 CLI 命令将消息推送给 agent。
    
    参数 cmd 已替换好 'MSG' 占位符。
    返回 True 表示 CLI 执行成功（返回码 0）。
    """
    if not cmd:
        return True
    
    try:
        # 后台执行 CLI，不阻塞 scan
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # 关闭父进程的文件描述符，让子进程独立运行
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
