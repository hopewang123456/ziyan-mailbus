"""Router dispatch — start_executing / await_plan_approval / first-step inbox push."""

from __future__ import annotations

from lib.application.orchestration.step_dispatch import dispatch_fsm_step
from lib.composition import get_fsm
from lib.domain.fsm import TaskFsmState
from lib.infra.utils import json_write


def _fsm():
    return get_fsm()


def set_await_plan_approval(task: dict) -> None:
    _fsm().ensure(task)
    task["fsm"]["state"] = TaskFsmState.CREATED.value
    task["fsm"]["substate"] = "await_plan_approval"
    task["status"] = "pending"


def start_executing(task: dict) -> None:
    _fsm().ensure(task)
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"].pop("substate", None)
    task["fsm"].pop("gate_id", None)
    task["status"] = "running"


def dispatch_first_step(data_dir: str, task: dict) -> bool:
    """Push chain[0] to assignee inbox; mark step dispatched."""
    chain = task.get("chain") or []
    if not chain:
        return False
    step = chain[0]
    tid = task.get("task_id") or task.get("id") or ""
    if not step.get("to_agent") and not step.get("to_person"):
        try:
            from lib.application.orchestration.dispatch.role_resolver import resolve_agent_for_role_type

            rt = int(step.get("role_type") or 0)
            pin = step.get("pin_agent") or step.get("agent_id")
            agent_id, meta = resolve_agent_for_role_type(data_dir, rt, pin_agent=pin)
            if agent_id:
                step["to_agent"] = agent_id
                step["dispatch_meta"] = meta
        except Exception:
            pass

    ok = dispatch_fsm_step(
        data_dir,
        tid,
        step,
        summary=task.get("intent") or task.get("summary") or "",
    )
    if ok:
        _fsm().mark_step_dispatched(step)
        task["fsm"]["active_step_id"] = step.get("step_id")
        task["assignee"] = step.get("to_agent") or step.get("to_person") or ""
        try:
            from lib.application.orchestration.tracker import TaskTracker

            tr = TaskTracker(data_dir)
            json_write(tr._task_path(tid), task)
        except Exception:
            pass
    return ok
