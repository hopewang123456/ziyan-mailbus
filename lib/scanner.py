"""
ziyan-mailbus scanner

扫描所有 agent 的 inbox，检测未读消息，构建推送队列（加急/普通）。
"""

import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

from .models import Message, MsgStatus, Priority, Inbox
from .utils import json_read, json_write, resolve_paths, _now_iso


def _scan_one_agent(data_dir: str, name: str, inbox_base: str) -> Optional[Tuple[str, list, list]]:
    """
    扫描单个 agent 的 inbox。
    
    返回: (agent_name, urgent_messages, normal_messages) 或 None（无待处理消息）
    """
    inbox_path = f"{inbox_base}/{name}/inbox.json"
    if not os.path.exists(inbox_path):
        return None
    
    inbox_data = json_read(inbox_path, {})
    if not inbox_data:
        return None
    
    inbox = Inbox.from_dict(inbox_data)
    
    # 检测该 agent 是否有回复消息（来自 agent 自己的回复）
    replied_ids = set()
    for m_raw in inbox.messages:
        msg_type = inbox.msg_field(m_raw, 'type', '')
        msg_from = inbox.msg_field(m_raw, 'from', '')
        msg_id = inbox.msg_field(m_raw, 'id', '')
        original_msg_id = inbox.msg_field(m_raw, 'original_msg_id', '') or msg_id
        
        if msg_type in ("reply", "forward") and msg_from == name:
            replied_ids.add(original_msg_id)
            if msg_id != original_msg_id:
                replied_ids.add(msg_id)
    
    if replied_ids:
        from datetime import datetime
        ts = datetime.now().isoformat()
        for m_raw in inbox.messages:
            mid = inbox.msg_field(m_raw, 'id', '')
            if mid in replied_ids:
                mstatus = inbox.msg_field(m_raw, 'status', '')
                if mstatus in (MsgStatus.PENDING, MsgStatus.PUSHED):
                    inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, acknowledged_at=ts)
                    mtype = inbox.msg_field(m_raw, 'type', '')
                    if not inbox.msg_field(m_raw, 'state'):
                        inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED,
                                             state=MsgStatus.RECEIVED, received_at=ts)
                        if mtype not in ("task", "task_reply"):
                            inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED,
                                                 state=MsgStatus.DONE, done_at=ts)
        json_write(inbox_path, inbox.to_dict())
    
    urgent_msgs = []
    normal_msgs = []
    has_pending = False
    
    for m_raw in inbox.messages:
        msg = Message.from_dict(m_raw) if isinstance(m_raw, dict) else m_raw
        if msg.status == MsgStatus.PENDING:
            has_pending = True
            if msg.priority == Priority.URGENT:
                urgent_msgs.append(msg)
            else:
                normal_msgs.append(msg)
    
    if has_pending:
        return (name, urgent_msgs, normal_msgs)
    return None


def scan_all(data_dir: str, agents: dict, max_workers: int = 4) -> List[Tuple[str, list, list]]:
    """
    并行扫描所有 agent 的 inbox。
    
    参数:
        data_dir: 数据目录
        agents: agent 配置字典
        max_workers: 最大并行线程数（默认 4）
    
    返回: [(agent_name, urgent_messages, normal_messages), ...]
    按加急在前、普通在后排序。
    """
    paths = resolve_paths(data_dir)
    inbox_base = paths['inbox']
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scan_one_agent, data_dir, name, inbox_base): name
            for name in agents
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception:
                pass  # 单个 agent 扫描失败不影响其他
    
    # 排序：有加急的 agent 排前面
    results.sort(key=lambda x: -len(x[1]))
    return results


def run_housekeeping(data_dir: str, agents: dict):
    """
    执行邮件系统的运维任务（非扫描核心职责）。
    由 bus.py 的 scan 命令在 build_queues 之后主动调用。

    包括：
    - 超时催办检测
    - skill 使用记录消费
    - agent 离线检测
    - 自动归档
    - 索引更新
    """
    paths = resolve_paths(data_dir)

    # 超时检测：检查所有 agent 的 inbox，超时未处理的消息自动催办
    _check_timeouts(data_dir, agents, paths['inbox'], paths)

    # Tracker 催办检测：检查 tracker 中 running 任务是否需要催办
    try:
        from .tracker import TaskTracker
        tracker = TaskTracker(data_dir)
        escalated = tracker.check_reminders(agents, reminder_minutes=5, max_reminders=3)
        if escalated:
            for e in escalated:
                print(f"  ⏰ 催办: {e['agent']} — {e['summary'][:40]}")
                # 写催办通知到目标 inbox
                escalate_file = f"{paths['inbox']}/{e['agent']}/inbox.json"
                if os.path.exists(os.path.dirname(escalate_file)):
                    e_data = json_read(escalate_file, {})
                    e_inbox = Inbox.from_dict(e_data) if e_data else Inbox(agent=e['agent'])
                    import time as _time
                    remind_msg = {
                        "id": f"tracker-remind-{int(_time.time())}",
                        "from": "mailbus",
                        "to": e['agent'],
                        "type": "notice",
                        "priority": "urgent",
                        "status": "pending",
                        "content": f"⏰ 催办提醒：任务「{e['summary']}」已超过催办时间，请尽快处理（第{e['reminded_count']}次催办）",
                        "created_at": _now_iso(),
                    }
                    e_inbox.messages.append(remind_msg)
                    e_inbox.has_unread = True
                    json_write(escalate_file, e_inbox.to_dict())
    except Exception as exc:
        print(f"  [scanner] tracker 催办异常: {exc}")

    # 技能使用记录消费：扫描 skill-usage-pending 目录，归入 skill-usage.json
    _consume_skill_usage(data_dir)

    # agent 离线检测：检查所有 agent 心跳，离线超过 3 次 ping 的发送通知
    _check_offline_agents(data_dir, agents, paths)

    # 自动归档：acknowledged 超过 7 天或 inbox 超过 300 条的消息
    try:
        from .archiver import archive_all
        archived = archive_all(data_dir, agents, archive_days=7, max_messages=300)
        if archived:
            for name, count in archived.items():
                print(f"  📦 {name}: {count} 条已归档")
    except Exception:
        pass

    # 自动索引：扫描所有 inbox 更新搜索索引
    try:
        from .search import scan_and_index
        scan_and_index(data_dir, agents)
    except Exception:
        pass


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
            msg = Message.from_dict(m_raw) if isinstance(m_raw, dict) else m_raw
            
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
                        
                        # 更新原消息的催办记录（使用 Inbox 统一访问器）
                        inbox.set_msg_status(msg.id, inbox.msg_field(m_raw, 'state', ''),
                                             reminded_count=(inbox.msg_field(m_raw, 'reminded_count', 0) or 0) + 1,
                                             last_reminded_at=datetime.now(timezone.utc).isoformat())
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
    inbox = Inbox.from_dict(inbox_data) if "agent" in inbox_data else None
    if not inbox:
        # 原始 dict 无法构造 Inbox，手动遍历
        acked = set()
        for m in inbox_data.get("messages", []):
            status = m.get("status") if isinstance(m, dict) else getattr(m, 'status', '')
            mid = m.get("id") if isinstance(m, dict) else getattr(m, 'id', '')
            if status == MsgStatus.ACKNOWLEDGED:
                acked.add(mid)
        return acked
    return {inbox.msg_field(m, 'id', '') for m in inbox.messages
            if inbox.msg_field(m, 'status', '') == MsgStatus.ACKNOWLEDGED}


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
    
    for mid in msg_ids:
        if inbox.set_msg_status(mid, MsgStatus.PUSHED):
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
    extra = {}
    if new_status == MsgStatus.ACKNOWLEDGED:
        extra["acknowledged_at"] = _now_iso()
    
    found = inbox.set_msg_status(msg_id, new_status, **extra)
    
    if found:
        json_write(inbox_file, inbox.to_dict())
    
    return found


def _check_offline_agents(data_dir: str, agents: dict, paths: dict):
    """检测离线 agent，给对应发件人发通知"""
    from datetime import datetime, timezone, timedelta
    
    hb_file = f"{data_dir}/heartbeat.json"
    hb_data = json_read(hb_file, {})
    agent_statuses = hb_data.get("agents", {})
    now = datetime.now(timezone.utc)
    
    for name in agents:
        status_info = agent_statuses.get(name, {})
        if status_info.get("status") == "offline":
            missed = status_info.get("missed_pings", 0)
            if missed >= 3:
                # 检查是否已经发过离线通知
                notified_file = f"{data_dir}/notified_offline.json"
                notified = json_read(notified_file, {})
                last_notified = notified.get(name, "")
                if last_notified:
                    try:
                        last = datetime.fromisoformat(last_notified)
                        if (now - last).total_seconds() < 3600:  # 1小时内不再重复通知
                            continue
                    except (ValueError, TypeError):
                        pass
                
                # 发通知给发件人
                escalate_to = "lingzhao"  # 默认通知灵昭
                escalate_file = f"{paths['inbox']}/{escalate_to}/inbox.json"
                if os.path.exists(os.path.dirname(escalate_file)):
                    try:
                        e_data = json_read(escalate_file, {})
                        e_inbox = Inbox.from_dict(e_data) if e_data else Inbox(agent=escalate_to)
                        import time as _time
                        warn_msg = {
                            "id": f"offline-{int(_time.time())}-{name}",
                            "from": "mailbus",
                            "to": escalate_to,
                            "type": "notice",
                            "priority": "urgent",
                            "status": MsgStatus.PENDING,
                            "content": f"⚠️ Agent 离线通知：{name} 已离线，连续 {missed} 次心跳未响应。",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                        e_inbox.messages.append(warn_msg)
                        e_inbox.has_unread = True
                        json_write(escalate_file, e_inbox.to_dict())
                        
                        # 更新已通知记录
                        notified[name] = datetime.now(timezone.utc).isoformat()
                        json_write(notified_file, notified)
                    except Exception:
                        pass
