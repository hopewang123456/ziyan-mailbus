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
    
    # 检查是否需要归档
    if len(inbox.messages) < max_messages:
        # 数量没超，检查是否有 7 天以上的已确认消息
        has_old = _has_old_acknowledged(inbox.messages, archive_days)
        if not has_old:
            return 0
    
    # 找出需要归档的消息（acknowledged 且满足条件）
    to_archive = []
    keep = []
    
    for m in inbox.messages:
        if isinstance(m, dict):
            should_archive = False
            if m.get("status") == MsgStatus.ACKNOWLEDGED:
                if len(inbox.messages) >= max_messages:
                    should_archive = True
                elif _is_old(m, archive_days):
                    should_archive = True
            
            if should_archive:
                to_archive.append(m)
            else:
                keep.append(m)
        else:
            keep.append(m)
    
    if not to_archive:
        return 0
    
    # 写入归档文件（按周分文件）
    week = datetime.now().strftime("%Y-W%V")
    archive_file = f"{paths['archive']}/{agent_name}/{week}.jsonl"
    os.makedirs(os.path.dirname(archive_file), exist_ok=True)
    
    for m in to_archive:
        m["status"] = MsgStatus.ARCHIVED
        jsonl_append(archive_file, m)
    
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
    """检查是否有 7 天以上的已确认消息"""
    for m in messages:
        if isinstance(m, dict) and m.get("status") == MsgStatus.ACKNOWLEDGED:
            if _is_old(m, archive_days):
                return True
    return False


def _is_old(msg: dict, archive_days: int) -> bool:
    """检查消息是否超过归档天数"""
    ack_at = msg.get("acknowledged_at")
    if not ack_at:
        return False
    
    try:
        # 解析 ISO 时间字符串
        ack_time = datetime.fromisoformat(ack_at)
        delta = datetime.now(timezone.utc) - ack_time.replace(tzinfo=timezone.utc) if ack_time.tzinfo is None else datetime.now(timezone.utc) - ack_time
        return delta.days >= archive_days
    except (ValueError, TypeError):
        return False
