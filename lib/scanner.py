"""
ziyan-mailbus scanner

扫描所有 agent 的 inbox，检测未读消息，构建推送队列（加急/普通）。
"""

import os
import json
from typing import List, Tuple

from .models import Message, MsgStatus, Priority, Inbox
from .utils import json_read, json_write, resolve_paths


def scan_all(data_dir: str, agents: dict) -> List[Tuple[str, list, list]]:
    """
    扫描所有 agent 的 inbox。
    
    返回: [(agent_name, urgent_messages, normal_messages), ...]
    按加急在前、普通在后排序。
    """
    paths = resolve_paths(data_dir)
    results = []
    
    for name in agents:
        inbox_path = f"{paths['inbox']}/{name}/inbox.json"
        if not os.path.exists(inbox_path):
            continue
        
        inbox_data = json_read(inbox_path, {})
        if not inbox_data:
            continue
        
        inbox = Inbox.from_dict(inbox_data)
        
        # 只处理未读且 pending 状态的消息
        urgent_msgs = []
        normal_msgs = []
        has_pending = False
        
        for m_raw in inbox.messages:
            if isinstance(m_raw, dict):
                msg = Message.from_dict(m_raw)
            else:
                msg = m_raw
            
            if msg.status == MsgStatus.PENDING:
                has_pending = True
                if msg.priority == Priority.URGENT:
                    urgent_msgs.append(msg)
                else:
                    normal_msgs.append(msg)
        
        if has_pending:
            results.append((name, urgent_msgs, normal_msgs))
    
    # 排序：有加急的 agent 排前面
    results.sort(key=lambda x: -len(x[1]))
    return results


def push_to_queue(data_dir: str, agent_name: str, messages: list, is_urgent: bool):
    """
    将待推送消息写入队列文件。
    队列文件格式: queue/urgent/<agent_name>.json 或 queue/normal/<agent_name>.json
    """
    paths = resolve_paths(data_dir)
    queue_dir = paths["queue_urgent"] if is_urgent else paths["queue_normal"]
    queue_file = f"{queue_dir}/{agent_name}.json"
    
    existing = json_read(queue_file, [])
    msg_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m for m in messages]
    existing.extend(msg_dicts)
    json_write(queue_file, existing)


def build_queues(data_dir: str, agents: dict) -> Tuple[dict, dict]:
    """
    完整流程：scan 全员的 inbox → 构建加急队列和普通队列。
    
    返回: (urgent_queue, normal_queue)
    每项: {agent_name: [Message, ...]}
    """
    urgent_queue = {}
    normal_queue = {}
    
    scanned = scan_all(data_dir, agents)
    
    for name, urgent_msgs, normal_msgs in scanned:
        if urgent_msgs:
            urgent_queue[name] = urgent_msgs
            push_to_queue(data_dir, name, urgent_msgs, is_urgent=True)
        if normal_msgs:
            normal_queue[name] = normal_msgs
            push_to_queue(data_dir, name, normal_msgs, is_urgent=False)
    
    return urgent_queue, normal_queue


def mark_as_pushed(data_dir: str, agent_name: str, msg_ids: list):
    """
    将 agent 的 inbox 中的 pending 消息标记为 pushed。
    """
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return
    
    inbox = Inbox.from_dict(inbox_data)
    changed = False
    
    for m in inbox.messages:
        if isinstance(m, dict):
            m_obj = Message.from_dict(m)
        else:
            m_obj = m
        
        if m_obj.id in msg_ids and m_obj.status == MsgStatus.PENDING:
            m_obj.status = MsgStatus.PUSHED
            if isinstance(m, dict):
                m.update(m_obj.to_dict())
            changed = True
    
    if changed:
        json_write(inbox_file, inbox.to_dict())


def update_message_status(data_dir: str, agent_name: str, msg_id: str, new_status: str):
    """
    更新 inbox 中单条消息的状态。
    """
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return False
    
    inbox = Inbox.from_dict(inbox_data)
    found = False
    
    for m in inbox.messages:
        if isinstance(m, dict):
            if m.get("id") == msg_id:
                m["status"] = new_status
                if new_status == MsgStatus.ACKNOWLEDGED:
                    from .utils import _now_iso
                    m["acknowledged_at"] = _now_iso()
                found = True
                break
    
    if found:
        json_write(inbox_file, inbox.to_dict())
    
    return found
