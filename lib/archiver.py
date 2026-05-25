"""
ziyan-mailbus archiver

将已确认的 inbox 消息归档到 archive/ 目录。
触发条件：acknowledged 后满 7 天 或 inbox 超过 300 条。
每人独立归档目录，按周分文件。
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from .models import MsgStatus, Inbox
from .utils import json_read, json_write, jsonl_append, resolve_paths, _now_iso


def archive_agent(data_dir: str, agent_name: str, archive_days: int = 7, max_messages: int = 300) -> int:
    """
    归档指定 agent 的已确认消息。
    
    返回归档的消息数量。
    """
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return 0
    
    inbox = Inbox.from_dict(inbox_data)
    
    def _get_status(m):
        return m.status if hasattr(m, 'status') else (m.get("status") if isinstance(m, dict) else None)
    
    def _is_acked(m):
        return _get_status(m) == MsgStatus.ACKNOWLEDGED
    
    # 找出需要归档的消息：acknowledged 且（超过数量限制 或 超过时间限制）
    acked_count = sum(1 for m in inbox.messages if _is_acked(m))
    
    if acked_count == 0:
        return 0
    
    should_archive_by_count = len(inbox.messages) >= max_messages
    should_archive_by_time = _has_old_acknowledged(inbox.messages, archive_days)
    
    if not should_archive_by_count and not should_archive_by_time:
        return 0
    
    to_archive = []
    keep = []
    
    for m in inbox.messages:
        if _is_acked(m):
            if _is_old(m, archive_days):
                # 超过时间限制 → 归档
                to_archive.append(m)
            else:
                keep.append(m)
        else:
            keep.append(m)
    
    # 如果按时间触发的归档后，inbox 仍然太多 → 按 ack 时间从旧到新再归档一批
    if should_archive_by_count and len(keep) >= max_messages:
        extra_keep = []
        from datetime import datetime, timezone
        keep.sort(key=lambda m: m.get("acknowledged_at", "") if isinstance(m, dict) else (m.acknowledged_at or ""))
        for i, m in enumerate(keep):
            if i < max_messages // 2:
                extra_keep.append(m)
            else:
                to_archive.append(m)
        keep = extra_keep
    
    if not to_archive:
        return 0
    
    # 写入归档文件（按周分文件）
    week = datetime.now().strftime("%Y-W%V")
    archive_file = f"{paths['archive']}/{agent_name}/{week}.jsonl"
    os.makedirs(os.path.dirname(archive_file), exist_ok=True)
    
    for m in to_archive:
        if hasattr(m, 'status'):
            m.status = MsgStatus.ARCHIVED
        else:
            m["status"] = MsgStatus.ARCHIVED
        msg_dict = m.to_dict() if hasattr(m, 'to_dict') else m
        jsonl_append(archive_file, msg_dict)
        # 同时写入搜索索引（如果在同一项目下）
        try:
            from .search import index_message
            index_message(data_dir, msg_dict)
        except (ImportError, Exception):
            pass
    
    # 更新 inbox
    inbox.messages = keep
    if not keep:
        inbox.has_unread = False
    json_write(inbox_file, inbox.to_dict())
    
    return len(to_archive)


def archive_all(data_dir: str, agents: dict, archive_days: int = 7, max_messages: int = 300) -> dict:
    """
    归档所有 agent 的已确认消息。
    
    返回: {agent_name: archived_count, ...}
    """
    results = {}
    for name in agents:
        count = archive_agent(data_dir, name, archive_days, max_messages)
        if count > 0:
            results[name] = count
    return results


def _has_old_acknowledged(messages: list, archive_days: int) -> bool:
    """检查是否有 archive_days 天以上的已确认消息"""
    for m in messages:
        status = m.status if hasattr(m, 'status') else (m.get("status") if isinstance(m, dict) else None)
        if status == MsgStatus.ACKNOWLEDGED:
            if _is_old(m, archive_days):
                return True
    return False


def _is_old(msg, archive_days: int) -> bool:
    """检查消息是否超过归档天数"""
    ack_at = msg.acknowledged_at if hasattr(msg, 'acknowledged_at') else (msg.get("acknowledged_at") if isinstance(msg, dict) else None)
    if not ack_at:
        return False
    
    try:
        # 解析 ISO 时间字符串
        ack_time = datetime.fromisoformat(ack_at)
        delta = datetime.now(timezone.utc) - ack_time.replace(tzinfo=timezone.utc) if ack_time.tzinfo is None else datetime.now(timezone.utc) - ack_time
        return delta.days >= archive_days
    except (ValueError, TypeError):
        return False
