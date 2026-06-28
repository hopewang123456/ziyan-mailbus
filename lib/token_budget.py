"""Token 预算 — 动态 scan 间隔、活动度探测、配置读取。"""

from __future__ import annotations

from typing import Any, Dict

from .constants import DEFAULT_CLI_MSG_MAX_CHARS
from .models import Inbox, MsgStatus
from .utils import json_read, resolve_paths

# 仍可能触发 CLI 推送的状态
_PUSHABLE_STATES = frozenset({
    MsgStatus.PENDING, MsgStatus.PUSHED, MsgStatus.PROCESSING,
    MsgStatus.ACKNOWLEDGED, MsgStatus.RECEIVED, MsgStatus.RESENDING,
    "pending", "pushed", "processing", "acknowledged", "received", "resending",
})

_DONE_STATES = frozenset({
    MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.ARCHIVED, MsgStatus.FAILED,
    "done", "closed", "archived", "failed",
})


def load_token_budget(config: dict) -> dict:
    """合并 token_budget 配置与合理默认值。"""
    tb = dict(config.get("token_budget") or {})
    defaults = {
        "scan_interval_idle_seconds": 300,
        "scan_interval_active_seconds": 180,
        "scan_interval_urgent_seconds": 120,
        "cli_msg_max_chars": config.get("cli_msg_max_chars", DEFAULT_CLI_MSG_MAX_CHARS),
        "cli_combined_max_chars": 4000,
        "memory_bridge_limit": 5,
        "memory_bridge_interval_seconds": 120,
        "patrol_interval_seconds": 3600,
        "summary_max_chars": 200,
    }
    for k, v in defaults.items():
        tb.setdefault(k, v)
    return tb


def measure_mailbus_activity(data_dir: str, agents: dict, config: dict) -> Dict[str, Any]:
    """统计 mailbus 活动度，供动态 scan 间隔使用。"""
    paths = resolve_paths(data_dir)
    pending = 0
    urgent = 0
    processing = 0

    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {}, ttl=0)
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        for m_raw in inbox.messages:
            state = (
                inbox.msg_field(m_raw, "state", "")
                or inbox.msg_field(m_raw, "status", "")
            ).lower()
            if state in _DONE_STATES:
                continue
            mtype = inbox.msg_field(m_raw, "type", "")
            action = inbox.msg_field(m_raw, "action", {}) or {}
            execute = action.get("execute", mtype == "task") if action else (mtype == "task")
            if mtype == "notice" and not execute:
                continue
            priority = (inbox.msg_field(m_raw, "priority", "") or "").lower()
            if state == MsgStatus.PROCESSING or state == "processing":
                processing += 1
            elif state in _PUSHABLE_STATES:
                pending += 1
                if priority == "urgent":
                    urgent += 1

    running_tasks = 0
    high_priority_tasks = 0
    interrupted_tasks = 0
    try:
        from .tracker import TaskTracker, TaskStatus
        running = TaskTracker(data_dir).list_all(status_filter=TaskStatus.RUNNING)
        running_tasks = len(running)
        from .task_fsm import ensure_fsm, task_priority
        for t in running:
            ensure_fsm(t)
            if task_priority(t) <= 25:
                high_priority_tasks += 1
            if t.get("interrupted"):
                interrupted_tasks += 1
    except Exception:
        pass

    if urgent > 0 or high_priority_tasks > 0 or interrupted_tasks > 0 or (running_tasks > 0 and pending > 0):
        level = "urgent"
    elif pending > 0 or processing > 0 or running_tasks > 0:
        level = "active"
    else:
        level = "idle"

    return {
        "level": level,
        "pending_messages": pending,
        "urgent_pending": urgent,
        "processing": processing,
        "running_tasks": running_tasks,
        "high_priority_tasks": high_priority_tasks,
        "interrupted_tasks": interrupted_tasks,
    }


def effective_scan_interval_seconds(config: dict, activity: Dict[str, Any]) -> int:
    tb = load_token_budget(config)
    level = activity.get("level", "idle")
    if level == "urgent":
        return int(tb["scan_interval_urgent_seconds"])
    if level == "active":
        return int(tb["scan_interval_active_seconds"])
    return int(tb["scan_interval_idle_seconds"])
