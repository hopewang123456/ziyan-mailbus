"""检测 pipeline 断链（CLI 退出 / task lock 过期）并触发 alerter。"""

from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from .self_heal import agent_cli_active_for
from lib.adapters.orchestration.task_fsm import StepFsmState, TaskFsmState, ensure_fsm, get_active_step, task_priority
from .task_lock import read_task_lock, task_lock_holder
from .tracker import TaskTracker, _parse_iso_dt
from .utils import _now_iso, json_write

_ACTIVE_STEP_STATES = frozenset({
    StepFsmState.DISPATCHED.value,
    StepFsmState.IN_PROGRESS.value,
    StepFsmState.AWAITING_RESULT.value,
    StepFsmState.QUEUED.value,
    "running",
})

_TERMINAL_TASK = frozenset({
    TaskFsmState.SUCCEEDED.value,
    TaskFsmState.CANCELLED.value,
    TaskFsmState.FAILED.value,
    "success",
    "failed",
    "timeout",
    "cancelled",
})


def _step_age_seconds(step: dict) -> float:
    ts = step.get("started_at") or step.get("updated_at") or ""
    if not ts:
        return 0.0
    try:
        dt = _parse_iso_dt(ts)
        return (now_utc_dt() - dt).total_seconds()
    except Exception:
        return 0.0


def detect_interrupted_tasks(
    data_dir: str,
    agents: dict,
    *,
    stale_seconds: float = 600.0,
    min_step_age: float = 180.0,
) -> List[dict]:
    """
    扫描 running pipeline：assignee CLI 不在线且步骤已等待超过 min_step_age → interrupted。
    返回本次新标记的任务摘要列表。
    """
    tr = TaskTracker(data_dir)
    flagged: List[dict] = []

    for task in tr.list_all():
        ensure_fsm(task)
        tid = task.get("task_id") or task.get("id") or ""
        if not tid:
            continue

        status = (task.get("status") or "").lower()
        fsm_state = (task.get("fsm") or {}).get("state") or ""
        if status in _TERMINAL_TASK or fsm_state in _TERMINAL_TASK:
            continue
        if fsm_state == TaskFsmState.PAUSED.value or status == "paused":
            continue
        if fsm_state == TaskFsmState.BLOCKED.value:
            continue

        step = get_active_step(task)
        if not step:
            continue
        step_state = step.get("fsm_state") or step.get("status") or ""
        if step_state not in _ACTIVE_STEP_STATES:
            continue

        assignee = step.get("to_person") or step.get("to_agent") or task.get("assignee") or ""
        if not assignee or assignee not in agents:
            continue

        age = _step_age_seconds(step)
        if age < min_step_age:
            continue

        if agent_cli_active_for(
            assignee, agents, task_id=tid,
        ):
            continue

        lock = read_task_lock(data_dir, tid)
        if lock:
            holder = lock.get("holder") or ""
            acquired = lock.get("acquired_at") or ""
            ttl = float(lock.get("ttl_seconds") or 3600)
            try:
                lock_age = (
                    now_utc_dt() - _parse_iso_dt(acquired)
                ).total_seconds()
            except Exception:
                lock_age = 0.0
            if lock_age < ttl and holder.startswith("mailbus"):
                continue

        if task.get("interrupted"):
            continue

        task["interrupted"] = True
        task.setdefault("fsm", {})["substate"] = "interrupted"
        hist = task["fsm"].setdefault("history", [])
        hist.append({
            "at": _now_iso(),
            "event": "interrupted",
            "assignee": assignee,
            "step_id": step.get("step_id"),
            "reason": "cli_inactive",
        })
        json_write(os.path.join(tr.tasks_dir, f"{tid}.json"), task)

        flagged.append({
            "task_id": tid,
            "assignee": assignee,
            "step_id": step.get("step_id"),
            "summary": (task.get("summary") or "")[:120],
            "age_seconds": round(age),
        })

        try:
            from .alerter import push_alert

            push_alert(
                data_dir,
                "interrupted",
                "warn",
                assignee,
                f"任务断链：{tid[:40]} · {assignee} CLI 无响应 · 步骤已等待 {int(age // 60)} 分钟",
                dedupe_key=f"interrupted:{tid}",
            )
        except Exception:
            pass

    return flagged


def count_high_priority_running(data_dir: str, *, threshold: int = 25) -> int:
    """FSM priority ≤ threshold 的 running 任务数（用于 urgent scan）。"""
    n = 0
    for task in TaskTracker(data_dir).list_all():
        if (task.get("status") or "") != "running":
            continue
        ensure_fsm(task)
        if task_priority(task) <= threshold:
            n += 1
    return n
