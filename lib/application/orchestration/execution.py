"""执行顺序编排 + 异常检测 — 保守去重，避免误 cancel 有效 pipeline。"""

from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from lib.models import Inbox, MsgStatus
from lib.tracker import TaskTracker, TaskStatus, _parse_iso_dt
from lib.utils import json_read, json_write, resolve_paths, _now_iso
from lib.self_heal import agent_cli_active

_TASK_ID_RE = re.compile(r"【([a-zA-Z0-9_-]+)】")
_ROUND2_MARKERS = ("Round2", "round-2-backlog", "iteration-r2", "R2-0")


def _primary_task_id(data_dir: str) -> str:
    st = json_read(os.path.join(data_dir, "iterations", "iteration-state.json"), {})
    return st.get("primary_task_id", "") or ""


def _round2_unlocked(data_dir: str) -> bool:
    gate = json_read(os.path.join(data_dir, "iterations", "round-1-gate.json"), {})
    if gate.get("round2_unlocked"):
        return True
    st = json_read(os.path.join(data_dir, "iterations", "iteration-state.json"), {})
    return bool(st.get("round2_unlocked"))


def _task_assignee(task: dict) -> str:
    chain = task.get("chain") or []
    if chain:
        return chain[-1].get("to_person") or task.get("assignee") or ""
    return task.get("assignee") or ""


def _is_business_pipeline(task: dict) -> bool:
    tid = task.get("task_id", "")
    if tid.startswith("msg-"):
        return False
    if task.get("requires_audit") is False and not task.get("chain"):
        return False
    return bool(task.get("chain"))


def _is_round2_dispatch(task: dict) -> bool:
    text = (task.get("summary") or "") + " " + (task.get("task_id") or "")
    return any(m in text for m in _ROUND2_MARKERS)


def _references_primary(task: dict, primary: str) -> bool:
    if not primary:
        return False
    tid = task.get("task_id", "")
    text = (task.get("summary") or "") + " " + tid
    return primary in text or "Round1" in text or "scheduler-validation" in text


def detect_anomalies(data_dir: str, agents: dict) -> List[dict]:
    """检测执行异常，供监控/告警使用。"""
    tr = TaskTracker(data_dir)
    primary = _primary_task_id(data_dir)
    paths = resolve_paths(data_dir)
    anomalies: List[dict] = []
    now = now_utc_dt()

    running = [t for t in tr.list_all() if t.get("status") == TaskStatus.RUNNING and _is_business_pipeline(t)]
    by_assignee: Dict[str, List[dict]] = defaultdict(list)
    for t in running:
        by_assignee[_task_assignee(t)].append(t)

    for person, tasks in by_assignee.items():
        if len(tasks) > 1:
            anomalies.append({
                "code": "duplicate_running",
                "severity": "warn",
                "agent": person,
                "detail": f"{len(tasks)} 条 pipeline 同时 running",
                "task_ids": [t.get("task_id") for t in tasks],
            })

    if primary:
        pt = tr.get(primary)
        if pt and pt.get("status") == TaskStatus.RUNNING:
            result = os.path.join(data_dir, "msg-results", f"{primary}.json")
            if not os.path.exists(result):
                assignee = _task_assignee(pt)
                if assignee and not agent_cli_active(assignee, agents):
                    anomalies.append({
                        "code": "primary_stalled_no_cli",
                        "severity": "critical",
                        "agent": assignee,
                        "detail": f"主任务 {primary} 无活跃 CLI",
                        "task_ids": [primary],
                    })

    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        proc_tasks = [
            m for m in inbox.messages
            if inbox.msg_field(m, "type", "") == "task"
            and inbox.msg_field(m, "state", "") in (MsgStatus.PROCESSING, MsgStatus.PUSHED)
        ]
        if len(proc_tasks) > 2:
            anomalies.append({
                "code": "inbox_processing_stack",
                "severity": "warn",
                "agent": name,
                "detail": f"{len(proc_tasks)} 条 task 处于 pushed/processing",
                "msg_ids": [inbox.msg_field(m, "id", "") for m in proc_tasks[:5]],
            })
        for m in proc_tasks:
            mid = inbox.msg_field(m, "id", "")
            ref = inbox.msg_field(m, "received_at", "") or inbox.msg_field(m, "created_at", "")
            if not ref:
                continue
            age_min = (now - _parse_iso_dt(ref).astimezone(timezone.utc)).total_seconds() / 60
            content = inbox.msg_field(m, "content", "")
            is_primary = primary and primary in content
            threshold = 8 if is_primary else 20
            if age_min > threshold and not agent_cli_active(name, agents):
                anomalies.append({
                    "code": "stale_processing",
                    "severity": "critical" if is_primary else "warn",
                    "agent": name,
                    "detail": f"{mid} processing {age_min:.0f}min 无 CLI",
                    "msg_ids": [mid],
                })

    if not _round2_unlocked(data_dir):
        r2_running = [
            t for t in running
            if _is_round2_dispatch(t) and not _references_primary(t, primary)
        ]
        if r2_running:
            anomalies.append({
                "code": "round2_ahead_of_gate",
                "severity": "warn",
                "detail": "Round2 任务在 Round1 门禁未通过时已 running",
                "task_ids": [t.get("task_id") for t in r2_running[:10]],
            })

    return anomalies


def _cancel_task(tr: TaskTracker, task_id: str, reason: str) -> bool:
    t = tr.get(task_id)
    if not t or t.get("status") != TaskStatus.RUNNING:
        return False
    t["status"] = TaskStatus.CANCELLED
    t["cancelled_at"] = _now_iso()
    t["cancel_reason"] = reason
    chain = t.get("chain") or []
    if chain and chain[-1].get("status") == "running":
        chain[-1]["status"] = "cancelled"
        chain[-1]["completed_at"] = _now_iso()
    json_write(tr._task_path(task_id), t)
    return True


def _reset_inbox_to_pending(data_dir: str, agent: str, msg_id: str, note: str) -> bool:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return False
    inbox = Inbox.from_dict(inbox_data)
    if inbox.set_msg_status(
        msg_id, MsgStatus.PENDING, state=MsgStatus.PENDING,
        pushed_count=0, done_at=None, done_note=note,
    ):
        inbox.has_unread = True
        json_write(inbox_file, inbox.to_dict())
        return True
    return False


def reconcile_execution_order(data_dir: str, agents: dict, *, mode: str = "light") -> dict:
    """
    保守编排（mode=light，默认）：
    - 永不 cancel 主任务或非 Round2 的 pipeline
    - 仅当 Round1 门禁未过 + 同 agent 有多条 Round2 msg-* 时，取消较旧的重复项
    - inbox：Round2 重复消息 reset 为 pending（非 done），便于后续 gate 通过后重推
    mode=off：只检测，不修改
    """
    if mode == "off":
        return {}

    tr = TaskTracker(data_dir)
    primary = _primary_task_id(data_dir)
    gate_open = _round2_unlocked(data_dir)
    stats = {
        "cancelled_tasks": 0,
        "reset_inbox": 0,
        "kept_primary": primary or None,
        "mode": mode,
    }

    if gate_open:
        return stats

    # 仅处理 Round2 重复 tracker（门禁未过）
    running_r2 = [
        t for t in tr.list_all()
        if t.get("status") == TaskStatus.RUNNING
        and t.get("task_id", "").startswith("msg-")
        and _is_round2_dispatch(t)
        and not _references_primary(t, primary)
    ]
    by_person: Dict[str, List[dict]] = defaultdict(list)
    for t in running_r2:
        by_person[_task_assignee(t)].append(t)

    for person, tasks in by_person.items():
        if len(tasks) <= 1:
            continue
        tasks_sorted = sorted(tasks, key=lambda t: t.get("created_at") or "")
        for drop in tasks_sorted[:-1]:
            tid = drop.get("task_id", "")
            if _cancel_task(tr, tid, "light: duplicate Round2 deferred until gate"):
                stats["cancelled_tasks"] += 1

    # inbox：Round2 重复 — 较旧 reset pending（保留最新一条）
    paths = resolve_paths(data_dir)
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        round2_msgs = []
        for m in inbox.messages:
            state = inbox.msg_field(m, "state", "")
            content = inbox.msg_field(m, "content", "")
            if inbox.msg_field(m, "type", "") != "task":
                continue
            if primary and primary in content:
                continue
            if not any(k in content for k in _ROUND2_MARKERS):
                continue
            # 已完成/已关闭的 Round2 不再 reset — 否则会每轮 scan 重推 LLM（token 黑洞）
            if state in (MsgStatus.DONE, MsgStatus.ARCHIVED, MsgStatus.CLOSED):
                continue
            round2_msgs.append(m)

        if len(round2_msgs) <= 1:
            continue
        round2_msgs.sort(key=lambda m: inbox.msg_field(m, "created_at", ""))
        for m in round2_msgs[:-1]:
            mid = inbox.msg_field(m, "id", "")
            state = inbox.msg_field(m, "state", "")
            if state in (MsgStatus.PENDING, MsgStatus.PROCESSING, MsgStatus.PUSHED):
                if _reset_inbox_to_pending(data_dir, name, mid, "light: defer duplicate Round2"):
                    stats["reset_inbox"] += 1

    return stats


def restore_cancelled_task(data_dir: str, task_id: str, reason: str = "manual restore") -> bool:
    """恢复被误 cancel 的 running pipeline。"""
    tr = TaskTracker(data_dir)
    t = tr.get(task_id)
    if not t or t.get("status") != TaskStatus.CANCELLED:
        return False
    t["status"] = TaskStatus.RUNNING
    t.pop("cancel_reason", None)
    t.pop("cancelled_at", None)
    chain = t.get("chain") or []
    if chain:
        chain[-1]["status"] = "running"
        chain[-1].pop("completed_at", None)
    t["restored_at"] = _now_iso()
    t["restore_reason"] = reason
    json_write(tr._task_path(task_id), t)
    return True


def run_orchestrator(data_dir: str, agents: dict, *, fix: bool = True, mode: str = "light") -> dict:
    """编排入口：检测 + 可选修复（默认 light 保守模式）。"""
    report = {
        "anomalies": detect_anomalies(data_dir, agents),
        "reconcile": {},
        "anomaly_count": 0,
    }
    report["anomaly_count"] = len(report["anomalies"])
    if fix:
        report["reconcile"] = reconcile_execution_order(data_dir, agents, mode=mode)
    return report
