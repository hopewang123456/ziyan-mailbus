"""Task 断链恢复 — mailbus recover --continue 与 Dashboard 继续。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from lib.adapters.orchestration.task_fsm import (
    StepFsmState,
    TaskFsmState,
    apply_pause,
    ensure_fsm,
    get_active_step,
    mark_step_dispatched,
)
from .task_lock import acquire_task_lock, release_task_lock, task_lock_holder
from .tracker import TaskTracker
from .utils import _now_iso, json_read, json_write, resolve_paths


def _append_recover_history(task: dict, event: str, detail: dict) -> None:
    fsm = task.setdefault("fsm", {})
    hist = fsm.setdefault("history", [])
    hist.append({"at": _now_iso(), "event": event, **detail})


def recover_continue(
    data_dir: str,
    task_id: str,
    *,
    reason: str = "manual_continue",
    holder: str = "mailbus-recover",
) -> Dict[str, Any]:
    """
    interrupted / paused / blocked 任务：同 step 重 push。
    成功返回 {ok, action, dispatch_ok, task_id, step_id}。
    """
    tr = TaskTracker(data_dir)
    task = tr.get(task_id)
    if not task:
        return {"ok": False, "error": "not_found"}

    ensure_fsm(task)
    fsm_state = (task.get("fsm") or {}).get("state", "")

    if fsm_state == TaskFsmState.CANCELLED.value:
        return {"ok": False, "error": "cancelled"}
    if fsm_state == TaskFsmState.SUCCEEDED.value:
        return {"ok": False, "error": "already_succeeded"}

    if fsm_state == TaskFsmState.PAUSED.value:
        task["fsm"]["state"] = TaskFsmState.EXECUTING.value
        task["status"] = "running"
        task.pop("pause_reason", None)

    step = get_active_step(task)
    if not step:
        chain = task.get("chain") or []
        for s in reversed(chain):
            if isinstance(s, dict) and s.get("fsm_state") not in (
                StepFsmState.COMPLETED.value,
                StepFsmState.SKIPPED.value,
                StepFsmState.SUPERSEDED.value,
            ):
                step = s
                break
    if not step:
        return {"ok": False, "error": "no_recoverable_step"}

    existing_holder = task_lock_holder(data_dir, task_id)
    if existing_holder and existing_holder != holder:
        return {"ok": False, "error": "task_locked", "holder": existing_holder}

    if not acquire_task_lock(data_dir, task_id, holder, meta={"action": "recover_continue"}):
        return {"ok": False, "error": "lock_failed"}

    try:
        step["fsm_state"] = StepFsmState.QUEUED.value
        step["status"] = "running"
        step.pop("result_consumed", None)
        task["fsm"]["state"] = TaskFsmState.EXECUTING.value
        task["fsm"]["active_step_id"] = step.get("step_id")
        task["status"] = "running"
        task["interrupted"] = False
        _append_recover_history(task, "recover_continue", {
            "reason": reason,
            "step_id": step.get("step_id"),
        })

        task_file = os.path.join(tr.tasks_dir, f"{task_id}.json")
        json_write(task_file, task)

        dispatch_ok = _repush_step(data_dir, task_id, task, step)
        if dispatch_ok:
            mark_step_dispatched(step)
            json_write(task_file, task)

        return {
            "ok": True,
            "action": "recover_continue",
            "task_id": task_id,
            "step_id": step.get("step_id"),
            "dispatch_ok": dispatch_ok,
            "to_person": step.get("to_person") or step.get("to_agent"),
        }
    finally:
        release_task_lock(data_dir, task_id, holder)


def apply_cancel_task(
    data_dir: str,
    task_id: str,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    """CLI/API 取消：apply_cancel + 释放 task lock。"""
    from lib.adapters.orchestration.task_fsm import apply_cancel

    tr = TaskTracker(data_dir)
    task = tr.get(task_id)
    if not task:
        return {"ok": False, "error": "not_found"}
    outcome = apply_cancel(
        task, reason=reason or "cancelled", data_dir=data_dir,
        agents=json_read(os.path.join(data_dir, "config.json"), {}).get("agents"),
    )
    if outcome.get("ok"):
        json_write(os.path.join(tr.tasks_dir, f"{task_id}.json"), task)
        lock = task_lock_holder(data_dir, task_id)
        if lock:
            release_task_lock(data_dir, task_id, lock)
    return outcome


def _repush_step(data_dir: str, task_id: str, task: dict, step: dict) -> bool:
    from lib.application.orchestration.pipeline.trigger import _send_task

    paths = resolve_paths(data_dir)
    to_person = step.get("to_agent") or step.get("to_person") or task.get("assignee") or ""
    if not to_person:
        return False
    summary = step.get("summary") or task.get("summary") or f"继续任务 {task_id}"
    return _send_task(
        data_dir,
        paths,
        from_person=step.get("from_agent") or "mailbus",
        from_role=step.get("from_role") or "调度",
        to_role=step.get("to_role") or "",
        to_person=to_person,
        summary=summary,
        task_id=task_id,
        step_num=int(step.get("step") or 1),
        step_id=step.get("step_id"),
        result_ref=step.get("result_ref"),
    )
