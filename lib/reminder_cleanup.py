"""陈旧催办 notice 自动关闭 — 任务已终态/暂停时清理 inbox 噪音。"""

from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import re
from datetime import datetime, timezone
from typing import Dict, Set

from .models import Inbox, MsgStatus
from .tracker import TaskTracker, _parse_iso_dt
from .utils import json_read, json_write, resolve_paths, _now_iso

REMIND_PREFIXES = ("remind-", "tracker-remind", "exec-remind-")
TERMINAL_TASK_STATUS = frozenset({
    "success", "cancelled", "failed", "timeout", "paused",
})
TERMINAL_FSM_STATES = frozenset({
    "succeeded", "cancelled", "failed", "paused", "blocked",
})
_TASK_BRACKET_RE = re.compile(r"【([^】]{4,120})】")
_TASK_QUOTE_RE = re.compile(r"任务「([^」]{4,120})」")


def _is_remind_message(mid: str, content: str) -> bool:
    if any(mid.startswith(p) for p in REMIND_PREFIXES):
        return True
    if "催办提醒" in content or "超时提醒" in content:
        return True
    return False


def _extract_task_refs(msg: dict, content: str) -> Set[str]:
    refs: Set[str] = set()
    tid = msg.get("task_id") or msg.get("related_task_id") or ""
    if tid:
        refs.add(str(tid).strip())
    for pat in (_TASK_BRACKET_RE, _TASK_QUOTE_RE):
        for m in pat.finditer(content or ""):
            refs.add(m.group(1).strip())
    mid = msg.get("id") or msg.get("in_response_to") or ""
    if isinstance(mid, str) and mid.startswith("msg-"):
        refs.add(mid)
    return {r for r in refs if r}


def _task_is_stale_for_remind(task: dict) -> bool:
    if not task:
        return True
    status = (task.get("status") or "").lower()
    if status in TERMINAL_TASK_STATUS:
        return True
    fsm_state = (task.get("fsm") or {}).get("state", "")
    if fsm_state in TERMINAL_FSM_STATES:
        return True
    return False


def _msg_age_minutes(msg: dict) -> float:
    ref = msg.get("created_at") or msg.get("received_at") or ""
    if not ref:
        return 0.0
    try:
        now = now_utc_dt()
        dt = _parse_iso_dt(ref)
        return (now - dt.astimezone(timezone.utc)).total_seconds() / 60.0
    except Exception:
        return 0.0


def close_stale_reminders(data_dir: str, agents: dict) -> Dict[str, int]:
    """关闭指向已终态/不存在任务的催办 notice。返回 {agent: closed_count}。"""
    paths = resolve_paths(data_dir)
    tracker = TaskTracker(data_dir)
    tasks_by_id = {t.get("task_id", ""): t for t in tracker.list_all() if t.get("task_id")}
    stats: Dict[str, int] = {}
    ts = _now_iso()

    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {}, ttl=0)
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        changed = 0

        for m_raw in inbox.messages:
            state = (
                inbox.msg_field(m_raw, "state", "")
                or inbox.msg_field(m_raw, "status", "")
            ).lower()
            if state in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.ARCHIVED):
                continue
            mid = inbox.msg_field(m_raw, "id", "")
            content = inbox.msg_field(m_raw, "content", "") or ""
            if not _is_remind_message(mid, content):
                continue

            refs = _extract_task_refs(
                m_raw if isinstance(m_raw, dict) else {},
                content,
            )
            stale = False
            if refs:
                stale = all(_task_is_stale_for_remind(tasks_by_id.get(r)) for r in refs)
            elif _msg_age_minutes(m_raw if isinstance(m_raw, dict) else {}) > 60:
                stale = True

            if not stale:
                continue
            if inbox.set_msg_status(
                mid,
                MsgStatus.ACKNOWLEDGED,
                state=MsgStatus.DONE,
                done_at=ts,
                done_note="auto: stale remind closed",
                acknowledged_at=ts,
            ):
                changed += 1

        if changed:
            json_write(inbox_file, inbox.to_dict())
            stats[name] = changed

    return stats
