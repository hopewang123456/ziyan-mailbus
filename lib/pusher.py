"""
ziyan-mailbus pusher

从队列读取待推送消息，通过 CLI 推送给 agent，等待 ack。
"""

import os
import subprocess
import json
import time
from typing import Optional

from .models import Message, MsgStatus, Priority
from .utils import json_read, json_write, jsonl_append, log_error, resolve_paths, _now_iso
from .scanner import mark_as_pushed


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
        cli_cmd: CLI 命令模板（实际消息内容会追加）
        ack_timeout: 等待 ack 超时（秒）
        max_retries: 最大重试次数（不含首次推送）
    
    返回:
        推送失败的消息 ID 列表
    """
    failed_ids = []
    msg_ids = [m.id if hasattr(m, 'id') else m["id"] for m in messages]
    
    # 1. 标记为 pushed
    mark_as_pushed(data_dir, agent_name, msg_ids)
    
    # 2. 构建推送内容（将所有未读消息一次推过去）
    msg_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m for m in messages]
    payload = json.dumps(msg_dicts, ensure_ascii=False)
    
    # 3. CLI 推送
    success = _invoke_cli(cli_cmd, payload)
    
    if success:
        # 等待 ack
        ack_received = _wait_for_ack(data_dir, agent_name, msg_ids, ack_timeout)
        
        if ack_received:
            # 所有消息已 ack
            return []
        
        # 部分/全部未 ack，进入重试
        unacked = _get_unacked_ids(data_dir, agent_name, msg_ids)
        
        for attempt in range(1, max_retries + 1):
            if not unacked:
                break
            
            # 附上断线说明
            retry_payload = json.dumps({
                "retry": True,
                "note": "这是之前推送但未收到确认的消息，请确认是否已完成或需要继续执行",
                "messages": [m for m in msg_dicts if m["id"] in unacked],
            }, ensure_ascii=False)
            
            success = _invoke_cli(cli_cmd, retry_payload)
            if success:
                ack_received = _wait_for_ack(data_dir, agent_name, unacked, ack_timeout)
                if ack_received:
                    unacked = _get_unacked_ids(data_dir, agent_name, unacked)
                else:
                    time.sleep(5)  # 重试间隔
            else:
                time.sleep(5)
        
        failed_ids = unacked
    else:
        # CLI 调用失败，直接标记所有消息为 failed
        failed_ids = msg_ids
    
    # 4. 处理失败
    if failed_ids:
        paths = resolve_paths(data_dir)
        for fid in failed_ids:
            _update_status_direct(data_dir, agent_name, fid, MsgStatus.FAILED)
            log_error(paths["errors"], fid, agent_name,
                      f"CLI 推送失败（{max_retries} 次重试均无 ack）")
    
    return failed_ids


def _invoke_cli(cli_cmd: str, payload: str) -> bool:
    """
    调用 CLI 将消息推送给 agent。
    
    返回 True 表示 CLI 执行成功（返回码 0），
    不代表 agent 已收到（ack 由 ack_handler 处理）。
    """
    if not cli_cmd:
        # 没有 CLI 配置，记录消息到 sent.json 由 agent 自行轮询
        return True
    
    try:
        # 用 stdin 传 payload（避免 shell 转义问题）
        full_cmd = f"echo '{payload}' | {cli_cmd}"
        result = subprocess.run(
            full_cmd,
            shell=True,
            timeout=15,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
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
