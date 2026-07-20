"""Pipeline 步骤结果校验 — 供 self_heal / scanner 共用。"""

from __future__ import annotations

from typing import Optional, Tuple

from .task_fsm import (
    ensure_fsm,
    get_active_step,
    read_step_result,
    result_applies_to_step,
)


def pipeline_step_result_matches(
    data_dir: str,
    task: dict,
    agent_name: str,
    *,
    require_consumed: bool = False,
) -> Tuple[bool, str]:
    """当前 running pipeline 步骤是否已有有效 msg-results。"""
    if not task or task.get("status") != "running":
        return False, "task_not_running"
    ensure_fsm(task)
    step = get_active_step(task)
    if not step or step.get("to_person") != agent_name:
        return False, "not_assignee"
    if step.get("status") not in ("running", None) and step.get("fsm_state") not in (
        "awaiting_result", "in_progress", "dispatched", "queued", None,
    ):
        if step.get("status") != "running":
            return False, "step_not_running"
    tid = task.get("task_id") or task.get("id") or ""
    result = read_step_result(data_dir, tid, step)
    if not result:
        return False, "missing_msg_results"
    ok, reason = result_applies_to_step(result, tid, step, task.get("chain") or [])
    if not ok:
        return False, reason
    if require_consumed and step.get("result_consumed") is not True:
        return False, "not_consumed"
    return True, "ok"


def has_valid_pipeline_result_for_agent(
    data_dir: str,
    task_id: str,
    agent_name: str,
    *,
    tasks_cache: Optional[list] = None,
) -> bool:
    """agent 是否已有对应当前 step 的有效结果（FSM + legacy）。"""
    from .tracker import TaskTracker

    task = None
    if tasks_cache:
        task = next((t for t in tasks_cache if (t.get("task_id") or t.get("id")) == task_id), None)
    if not task:
        task = TaskTracker(data_dir).get(task_id)
    if not task:
        return False
    ok, _ = pipeline_step_result_matches(data_dir, task, agent_name)
    return ok
