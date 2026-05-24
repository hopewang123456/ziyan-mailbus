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
                        ts = __import__('datetime').datetime.now().isoformat()
                        if isinstance(m_raw, dict):
                            m_raw["status"] = MsgStatus.ACKNOWLEDGED
                            m_raw["acknowledged_at"] = ts
                            # v3.0 状态机流转
                            if not m_raw.get("state"):
                                m_raw["state"] = MsgStatus.RECEIVED
                                history = m_raw.get("state_history", [])
                                if not isinstance(history, list): history = []
                                history.append({"state": MsgStatus.RECEIVED, "at": ts})
                                m_raw["state_history"] = history
                                m_raw["received_at"] = ts
                            # 如果 type 不是 task，直接 done
                            if m_raw.get("type") not in ("task", "task_reply"):
                                m_raw["state"] = MsgStatus.DONE
                                m_raw["state_history"].append({"state": MsgStatus.DONE, "at": ts})
                                m_raw["done_at"] = ts
                        else:
                            m_raw.status = MsgStatus.ACKNOWLEDGED
                            m_raw.acknowledged_at = ts
                            if not m_raw.state:
                                m_raw.state = MsgStatus.RECEIVED
                                history = list(m_raw.state_history or [])
                                history.append({"state": MsgStatus.RECEIVED, "at": ts})
                                m_raw.state_history = history
                                m_raw.received_at = ts
                            if m_raw.type not in ("task", "task_reply"):
                                m_raw.state = MsgStatus.DONE
                                m_raw.state_history.append({"state": MsgStatus.DONE, "at": ts})
                                m_raw.done_at = ts
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
    
    # 超时检测：检查所有 agent 的 inbox，超时未处理的消息自动催办
    _check_timeouts(data_dir, agents, inbox_path.rsplit("/inbox/", 1)[0] + "/inbox" if "inbox_path" in dir() else data_dir + "/inbox", paths)
    
    # 技能使用记录消费：扫描 skill-usage-pending 目录，归入 skill-usage.json
    _consume_skill_usage(data_dir)
    
    return results


def _consume_skill_usage(data_dir: str):
    """扫描 skill-usage-pending/ 目录，消费待处理的 skill 使用记录"""
    pending_dir = os.path.join(data_dir, "skill-usage-pending")
    target_file = os.path.join(data_dir, "skill-usage.json")
    if not os.path.isdir(pending_dir):
        return
    
    consumed = 0
    target_data = json_read(target_file, {})
    
    for fname in os.listdir(pending_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(pending_dir, fname)
        try:
            with open(fpath) as f:
                record = json.load(f)
            skill = record.get("skill", "")
            agent = record.get("agent", "")
            ts = record.get("timestamp", "")
            if not skill or not agent:
                continue
            
            if skill not in target_data:
                target_data[skill] = {}
            if agent not in target_data[skill]:
                target_data[skill][agent] = {"use_count": 0, "view_count": 0, "last_used": ""}
            target_data[skill][agent]["use_count"] = target_data[skill][agent].get("use_count", 0) + 1
            if ts:
                target_data[skill][agent]["last_used"] = ts
            
            os.remove(fpath)
            consumed += 1
        except Exception:
            pass
    
    if consumed > 0:
        json_write(target_file, target_data)


def _check_timeouts(data_dir: str, agents: dict, inbox_base: str, paths: dict):
    """扫描所有 inbox，检测超时未处理的消息并催办"""
    from datetime import datetime, timezone, timedelta
    
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        if not os.path.exists(inbox_file):
            continue
        
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        
        inbox = Inbox.from_dict(inbox_data)
        now = datetime.now(timezone.utc)
        reminded = []
        
        for m_raw in inbox.messages:
            if isinstance(m_raw, dict):
                msg = Message.from_dict(m_raw)
            else:
                msg = m_raw
            
            timeout_min = msg.timeout_minutes
            if not timeout_min or timeout_min <= 0:
                continue
            if msg.state in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.REJECTED):
                continue
            
            # 计算已过去的时间
            created = None
            if msg.received_at:
                try:
                    created = datetime.fromisoformat(msg.received_at)
                except (ValueError, TypeError):
                    pass
            if not created and msg.created_at:
                try:
                    created = datetime.fromisoformat(msg.created_at)
                except (ValueError, TypeError):
                    pass
            if not created:
                continue
            
            elapsed_min = (now - created).total_seconds() / 60
            if elapsed_min < timeout_min:
                continue
            
            # 超时了，检查是否已经催办过（至少隔 timeout_min/2 才再次催办）
            if msg.reminded_count > 0:
                last_reminded = None
                if msg.last_reminded_at:
                    try:
                        last_reminded = datetime.fromisoformat(msg.last_reminded_at)
                    except (ValueError, TypeError):
                        pass
                if last_reminded and (now - last_reminded).total_seconds() / 60 < timeout_min / 2:
                    continue
            
            # 发催办通知
            escalate = msg.escalate_to or msg.from_
            if escalate and escalate not in ("mailbus", "broadcast", ""):
                escalate_file = f"{paths['inbox']}/{escalate}/inbox.json"
                if os.path.exists(os.path.dirname(escalate_file)):
                    try:
                        e_data = json_read(escalate_file, {})
                        e_inbox = Inbox.from_dict(e_data) if e_data else Inbox(agent=escalate)
                        import time as _time
                        remind_msg = {
                            "id": f"remind-{int(_time.time())}-{name}",
                            "from": "mailbus",
                            "to": escalate,
                            "type": "notice",
                            "priority": "urgent",
                            "status": MsgStatus.PENDING,
                            "content": f"⚠️ 超时提醒：{name} 有一条消息已超过 {int(timeout_min)} 分钟未处理。\n消息ID: {msg.id}\n请关注。",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                        e_inbox.messages.append(remind_msg)
                        e_inbox.has_unread = True
                        json_write(escalate_file, e_inbox.to_dict())
                        
                        # 更新原消息的催办记录
                        if isinstance(m_raw, dict):
                            m_raw["reminded_count"] = (m_raw.get("reminded_count", 0) or 0) + 1
                            m_raw["last_reminded_at"] = datetime.now(timezone.utc).isoformat()
                        else:
                            m_raw.reminded_count = (m_raw.reminded_count or 0) + 1
                            m_raw.last_reminded_at = datetime.now(timezone.utc).isoformat()
                        reminded.append(name)
                    except Exception:
                        pass
        
        if reminded:
            json_write(inbox_file, inbox.to_dict())


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
