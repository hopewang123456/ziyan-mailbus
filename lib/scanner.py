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
        
        # 检测该 agent 是否有回复消息（来自 agent 自己的回复）
        # 如果有，说明 agent 已经读了前面的消息，自动标为 acknowledged
        replied_ids = set()
        for m_raw in inbox.messages:
            if isinstance(m_raw, dict):
                msg_type = m_raw.get("type", "")
                msg_from = m_raw.get("from", "")
                original_msg_id = m_raw.get("original_msg_id") or m_raw.get("id", "")
            else:
                msg_type = m_raw.type
                msg_from = m_raw.from_
                original_msg_id = getattr(m_raw, 'original_msg_id', '') or m_raw.id
            
            # 如果 agent 发了 reply/forward 类型的消息，说明它已经读了
            if msg_type in ("reply", "forward") and msg_from == name:
                replied_ids.add(original_msg_id)
                # 也匹配 parent id
                if isinstance(m_raw, dict):
                    msg_id = m_raw.get("id", "")
                else:
                    msg_id = m_raw.id
                if msg_id != original_msg_id:
                    replied_ids.add(msg_id)
        
        # 如果有回复，找到对应的 pending 消息并标为 acknowledged
        if replied_ids:
            for m_raw in inbox.messages:
                if isinstance(m_raw, dict):
                    mid = m_raw.get("id", "")
                else:
                    mid = m_raw.id
                if mid in replied_ids and m_raw.get("status") if isinstance(m_raw, dict) else m_raw.status:
                    mstatus = m_raw.get("status") if isinstance(m_raw, dict) else m_raw.status
                    if mstatus == MsgStatus.PENDING or mstatus == MsgStatus.PUSHED:
                        if isinstance(m_raw, dict):
                            m_raw["status"] = MsgStatus.ACKNOWLEDGED
                            m_raw["acknowledged_at"] = __import__('datetime').datetime.now().isoformat()
                        else:
                            m_raw.status = MsgStatus.ACKNOWLEDGED
                            m_raw.acknowledged_at = __import__('datetime').datetime.now().isoformat()
            json_write(inbox_path, inbox.to_dict())
        
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


def _get_acked_ids(inbox_data: dict) -> set:
    """
    从 inbox 数据中提取已 ack 的消息 ID 集合。
    用于幂等去重。
    """
    acked = set()
    for m in inbox_data.get("messages", []):
        if isinstance(m, dict):
            if m.get("status") == MsgStatus.ACKNOWLEDGED:
                acked.add(m.get("id", ""))
        else:
            if getattr(m, 'status', '') == MsgStatus.ACKNOWLEDGED:
                acked.add(getattr(m, 'id', ''))
    return acked


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
        mid = m.id if hasattr(m, 'id') else (m.get("id") if isinstance(m, dict) else None)
        mstatus = m.status if hasattr(m, 'status') else (m.get("status") if isinstance(m, dict) else None)
        if mid in msg_ids and mstatus == MsgStatus.PENDING:
            if hasattr(m, 'status'):
                m.status = MsgStatus.PUSHED
            else:
                m["status"] = MsgStatus.PUSHED
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
        mid = m.id if hasattr(m, 'id') else (m.get("id") if isinstance(m, dict) else None)
        if mid == msg_id:
            if hasattr(m, 'status'):
                m.status = new_status
                if new_status == MsgStatus.ACKNOWLEDGED:
                    from .utils import _now_iso
                    m.acknowledged_at = _now_iso()
            else:
                m["status"] = new_status
                if new_status == MsgStatus.ACKNOWLEDGED:
                    from .utils import _now_iso
                    m["acknowledged_at"] = _now_iso()
            found = True
            break
    
    if found:
        json_write(inbox_file, inbox.to_dict())
    
    return found
