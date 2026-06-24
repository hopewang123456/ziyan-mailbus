"""Envelope 创建后首步 dispatch。"""

from __future__ import annotations

import os

from ..dispatch.role_resolver import resolve_agent_for_role_type
from ..dispatch.tier_filter import dispatch_action_from_envelope, dispatch_action_from_step
from ..fsm_dispatch import dispatch_fsm_step
from ..locale.role_labels import role_type_to_zh
from ..task_fsm import TaskFsmState, ensure_fsm, mark_step_dispatched
from ..utils import json_read, json_write


def start_executing(task: dict) -> None:
    ensure_fsm(task)
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["status"] = "running"


def set_await_plan_approval(task: dict) -> None:
    ensure_fsm(task)
    task["fsm"]["state"] = TaskFsmState.CREATED.value
    task["fsm"]["substate"] = "await_plan_approval"
    task["status"] = "pending"


def dispatch_first_step(data_dir: str, task: dict) -> bool:
    chain = task.get("chain") or []
    if not chain:
        return False
    step = chain[0]
    rt = step.get("role_type")
    if rt is None:
        return False

    pin = step.get("pin_agent")
    action = dispatch_action_from_step(step, task)
    agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}
    agent_id, meta = resolve_agent_for_role_type(
        data_dir, int(rt), pin_agent=pin, action=action, agents_cfg=agents_cfg,
    )
    step["to_agent"] = agent_id
    step["to_person"] = agent_id
    step["dispatch_meta"] = meta
    step.setdefault("to_role", role_type_to_zh(int(rt), data_dir))
    mark_step_dispatched(step)
    task["assignee"] = agent_id
    task["fsm"]["active_step_id"] = step.get("step_id")

    ok = dispatch_fsm_step(
        data_dir,
        task.get("task_id", ""),
        step,
        summary=task.get("intent") or task.get("summary") or "",
    )
    # dual_coding：并行第二步同时 dispatch
    if ok and len(chain) > 1 and chain[1].get("parallel_with") == "s1":
        ok2 = dispatch_fsm_step(
            data_dir,
            task.get("task_id", ""),
            chain[1],
            summary=task.get("intent") or task.get("summary") or "",
        )
        ok = ok and ok2
    if ok:
        task_path = __import__("os").path.join(data_dir, "tasks", f"{task['task_id']}.json")
        json_write(task_path, task)
    return ok
