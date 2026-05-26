"""
ziyan-mailbus ack_handler

处理 agent 回复的三种格式：
1. ack — 确认收到
2. mark_read — 仅标记已读
3. forward — 转发给其他 agent
"""

import os
import json
from typing import Optional

from .models import Message, MsgStatus, Priority, Inbox
from .utils import json_read, json_write, resolve_paths, build_message, _now_iso


def process_ack(data_dir: str, agent_name: str, ack_data: dict) -> bool:
    """
    处理 agent 的 ack 回复。
    
    ack_data 格式:
        {"action": "ack", "msg_id": "msg-xxx", "agent": "lingxiao", "timestamp": "..."}
    
    返回 True 表示处理成功。
    """
    msg_id = ack_data.get("msg_id")
    if not msg_id:
        return False
    
    # 校验 agent 时间戳 — 如果明显异常（早于2026年），用总线时间覆盖
    ts_raw = ack_data.get("timestamp", "")
    ts = ts_raw
    if ts_raw and ts_raw.startswith("2025"):
        ts = _now_iso()
    
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return False
    
    inbox = Inbox.from_dict(inbox_data)
    found = inbox.set_msg_status(msg_id, MsgStatus.ACKNOWLEDGED, acknowledged_at=ts)
    
    if found:
        # v3.0 状态机：ack → received（使用统一访问器）
        msg = inbox.get_msg(msg_id)
        if msg and not inbox.msg_field(msg, 'state'):
            inbox.set_msg_status(msg_id, MsgStatus.ACKNOWLEDGED,
                                 state=MsgStatus.RECEIVED,
                                 received_at=ts)
            # 非 task 类型直接 done
            mtype = inbox.msg_field(msg, 'type', '')
            if mtype not in ("task", "task_reply"):
                inbox.set_msg_status(msg_id, MsgStatus.ACKNOWLEDGED,
                                     state=MsgStatus.DONE,
                                     done_at=ts)
        
        # 检查 forward_chain，自动更新当前 agent 的 hop 状态
        for m in inbox.messages:
            if inbox.msg_field(m, 'id') == msg_id:
                fwd_chain = inbox.msg_field(m, 'forward_chain')
                if fwd_chain and fwd_chain.get("hops"):
                    for hop in fwd_chain["hops"]:
                        if hop.get("agent") == agent_name and hop.get("status") != "done":
                            hop["status"] = "done"
                            hop["at"] = ts
                            break
                    if all(h.get("status") == "done" for h in fwd_chain["hops"]):
                        fwd_chain["status"] = "completed"
                break
        
        inbox.has_unread = inbox.has_unread_messages()
        json_write(inbox_file, inbox.to_dict())

    return found


def process_mark_read(data_dir: str, agent_name: str, mark_data: dict) -> bool:
    """
    处理 agent 的 mark_read 回复。
    
    mark_data 格式:
        {"action": "mark_read", "msg_ids": ["msg-1", "msg-2"], "agent": "lingxiao", "timestamp": "..."}
    
    返回 True 表示至少有一条消息处理成功。
    """
    msg_ids = mark_data.get("msg_ids", [])
    if not msg_ids:
        return False
    
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return False
    
    inbox = Inbox.from_dict(inbox_data)
    changed = False
    timestamp = mark_data.get("timestamp", _now_iso())
    
    for msg_id in msg_ids:
        if inbox.set_msg_status(msg_id, MsgStatus.ACKNOWLEDGED, acknowledged_at=timestamp):
            changed = True
    
    if changed:
        inbox.has_unread = inbox.has_unread_messages()
        json_write(inbox_file, inbox.to_dict())
    
    return changed


def process_forward(data_dir: str, forward_data: dict) -> bool:
    """
    处理 agent 的 forward 回复。
    
    forward_data 格式:
        {
            "action": "forward",
            "original_msg_id": "msg-xxx",
            "from": "lingxiao",
            "to": "xiaoqi",
            "type": "task",
            "priority": "normal",
            "content": "...",
            "attachments": [],
            "timestamp": "..."
        }
    
    此函数直接将转发消息写入目标 agent 的 inbox，
    由下个 cron cycle 推送。
    """
    to = forward_data.get("to")
    if not to:
        return False
    
    paths = resolve_paths(data_dir)
    target_inbox_file = f"{paths['inbox']}/{to}/inbox.json"
    
    # 构建新消息
    new_msg = build_message(
        from_=forward_data.get("from", "unknown"),
        to=to,
        content=forward_data.get("content", ""),
        msg_type=forward_data.get("type", "task"),
        priority=forward_data.get("priority", "normal"),
        attachments=forward_data.get("attachments"),
    )
    new_msg.original_msg_id = forward_data.get("original_msg_id", "")
    
    # 写入目标 inbox
    inbox_data = json_read(target_inbox_file, {"agent": to, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(new_msg.to_dict())
    json_write(target_inbox_file, inbox.to_dict())
    
    return True


def scan_ack_files(data_dir: str, agents: dict) -> int:
    """
    扫描所有 agent 的 ack.json / mark.json，处理回复。
    
    返回处理的回复数量。
    """
    paths = resolve_paths(data_dir)
    total_processed = 0
    
    for name in agents:
        # 处理 ack.json
        ack_file = f"{paths['inbox']}/{name}/ack.json"
        ack_data = json_read(ack_file, None)
        if ack_data:
            if isinstance(ack_data, dict):
                ack_data = [ack_data]
            for entry in ack_data:
                if entry.get("action") == "ack":
                    if process_ack(data_dir, name, entry):
                        total_processed += 1
            
            # 清空 ack.json（保留空数组）
            json_write(ack_file, [])
        
        # 处理 mark.json
        mark_file = f"{paths['inbox']}/{name}/mark.json"
        mark_data = json_read(mark_file, None)
        if mark_data:
            if isinstance(mark_data, dict):
                mark_data = [mark_data]
            for entry in mark_data:
                if entry.get("action") == "mark_read":
                    if process_mark_read(data_dir, name, entry):
                        total_processed += 1
            
            json_write(mark_file, [])
    
    return total_processed


def scan_error_reports(data_dir: str, agents: dict) -> list:
    """
    扫描所有 inbox 中的 error_report 类型消息，更新任务状态。

    返回处理的错误回执列表 [{task_id, error_code, reason}]
    """
    paths = resolve_paths(data_dir)
    reports = []

    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue

        inbox = Inbox.from_dict(inbox_data)
        for m in inbox.messages:
            msg_type = inbox.msg_field(m, 'type', '')
            task_id = inbox.msg_field(m, 'task_id', '')
            error = inbox.msg_field(m, 'error', {})

            if msg_type == "error_report" and error and task_id:
                # 更新 tracker 任务状态为 failed
                try:
                    from .tracker import TaskTracker, TaskStatus
                    tracker = TaskTracker(data_dir)
                    tracker.update_status(task_id, TaskStatus.FAILED, error={
                        "code": error.get("code", "UNKNOWN"),
                        "reason": error.get("reason", ""),
                        "detail": error.get("trace", ""),
                        "agent": name,
                        "reported_at": _now_iso(),
                    })
                except Exception as e:
                    print(f"[ack_handler] tracker 更新失败: {e}")
                reports.append({
                    "task_id": task_id,
                    "agent": name,
                    "error_code": error.get("code", "UNKNOWN"),
                    "reason": error.get("reason", ""),
                })

    return reports


def scan_forward_files(data_dir: str, agents: dict) -> int:
    """
    扫描所有 agent 的 forward.json，处理转发请求。
    
    转发请求是 agent 直接写其他 agent 的 inbox 的，
    这里只处理通过 forward.json 显式投递的转发。
    
    返回处理的转发数量。
    """
    paths = resolve_paths(data_dir)
    total_processed = 0
    
    for name in agents:
        forward_file = f"{paths['inbox']}/{name}/forward.json"
        fwd_data = json_read(forward_file, None)
        if fwd_data:
            if isinstance(fwd_data, dict):
                fwd_data = [fwd_data]
            for entry in fwd_data:
                if entry.get("action") == "forward":
                    if process_forward(data_dir, entry):
                        total_processed += 1
            
            json_write(forward_file, [])
    
    return total_processed
