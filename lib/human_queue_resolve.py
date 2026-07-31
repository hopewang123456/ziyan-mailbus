"""human-queue resolve 后触发 workflow / FSM 副作用。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .human_queue import close_item, load_queue
from .tracker import TaskTracker
from .utils import json_read, json_write


def _find_pending_item(data_dir: str, item_id: str) -> Optional[dict]:
    for item in load_queue(data_dir).get("items") or []:
        if item.get("id") == item_id and item.get("status") == "pending":
            return item
    return None


def apply_human_queue_resolution(
    data_dir: str,
    item: dict,
    body: dict,
) -> Dict[str, Any]:
    """close_item 之后：按 type 路由 gate / FSM。"""
    qtype = item.get("type") or ""
    decision = (body.get("decision") or item.get("resolution", {}).get("decision") or "approved").lower()
    task_id = item.get("task_id") or ""
    gate_id = item.get("gate_id") or ""
    intake_id = item.get("intake_id") or ""
    outcome: Dict[str, Any] = {"routed": qtype}

    if qtype == "plan_approval" and task_id:
        from lib.application.orchestration.actions import apply_approve_plan

        tr = TaskTracker(data_dir)
        task = tr.get(task_id)
        if not task:
            return {"routed": qtype, "error": "task_not_found"}
        if decision == "denied":
            body = {**body, "action": body.get("action") or "replan"}
        result = apply_approve_plan(task, body, data_dir=data_dir)
        if result.get("ok"):
            json_write(os.path.join(data_dir, "tasks", f"{task_id}.json"), task)
        return {"routed": qtype, **result}

    if qtype == "owner_confirmation" and task_id:
        from lib.adapters.orchestration.task_fsm import TaskFsmState, ensure_fsm

        tr = TaskTracker(data_dir)
        task = tr.get(task_id)
        if not task:
            return {"routed": qtype, "error": "task_not_found"}
        ensure_fsm(task)
        if decision == "approved":
            task["fsm"]["state"] = TaskFsmState.EXECUTING.value
            task["fsm"].pop("substate", None)
            task["fsm"].pop("human_queue_id", None)
            task["status"] = "running"
            comment = body.get("comment") or body.get("brief") or ""
            if comment:
                task.setdefault("owner_clarifications", []).append({
                    "resolved_at": body.get("resolved_at"),
                    "comment": comment,
                })
            json_write(os.path.join(data_dir, "tasks", f"{task_id}.json"), task)
            return {"routed": qtype, "ok": True, "action": "resume_after_clarification"}
        task["fsm"]["state"] = TaskFsmState.CANCELLED.value
        task["fsm"].pop("substate", None)
        task["status"] = "cancelled"
        json_write(os.path.join(data_dir, "tasks", f"{task_id}.json"), task)
        return {"routed": qtype, "ok": True, "action": "cancelled_after_denial"}

    if qtype == "final_acceptance" and task_id:
        from lib.application.orchestration.actions import apply_accept

        tr = TaskTracker(data_dir)
        task = tr.get(task_id)
        if not task:
            return {"routed": qtype, "error": "task_not_found"}
        result = apply_accept(task, body, data_dir=data_dir)
        if result.get("ok"):
            json_write(os.path.join(data_dir, "tasks", f"{task_id}.json"), task)
        return {"routed": qtype, **result}

    if qtype == "a2a_input_required" and task_id:
        from .profile_registry import get_profile
        from .transport.dispatch_integration import build_router, merge_agent_transport_config
        from .transport.step_result_io import write_step_result_file
        from .transport.types import DispatchContext

        ctx_raw = item.get("context") or {}
        step_id = ctx_raw.get("step_id") or ""
        a2a_task_id = ctx_raw.get("a2a_task_id") or ""
        reviewer = body.get("reviewer") or ctx_raw.get("to_agent") or ""
        role_type = int(ctx_raw.get("role_type") or 0)
        if not reviewer or not step_id or not a2a_task_id:
            return {"routed": qtype, "error": "missing_a2a_context"}
        if decision == "denied":
            return {"routed": qtype, "ok": True, "action": "a2a_input_denied"}
        prof = get_profile(reviewer) or {}
        display = prof.get("display_name") or reviewer
        router = build_router(data_dir)
        agents = merge_agent_transport_config(
            json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}
        )
        agent_cfg = agents.get(reviewer) or {}
        if not role_type and agent_cfg.get("role_types"):
            role_type = int(agent_cfg["role_types"][0])
        ctx = DispatchContext(
            data_dir=data_dir,
            task_id=task_id,
            step_id=step_id,
            to_agent=reviewer,
            role_type=role_type,
            stub_fixture=ctx_raw.get("stub_fixture") or "path-c-input-required.json",
        )
        outcome = router.a2a.resume_after_resolve(
            ctx,
            a2a_task_id=a2a_task_id,
            agent_id=reviewer,
            display_name=display,
            role_type=ctx.role_type,
            comment=body.get("comment") or "",
            hq_id=item.get("id") or "",
            agents=agents,
        )
        if outcome.get("awaiting_human"):
            return {"routed": qtype, "ok": False, "error": "still_input_required"}
        if outcome.get("ok") and outcome.get("step_result"):
            write_step_result_file(
                data_dir, task_id, step_id, outcome["step_result"],
                agent=reviewer, role_type=ctx.role_type,
            )
            from lib.application.orchestration.pipeline.trigger import trigger_task

            trigger_task(data_dir, task_id, agents, __import__("lib.utils", fromlist=["resolve_paths"]).resolve_paths(data_dir))
            return {"routed": qtype, "ok": True, "action": "a2a_resumed"}
        return {"routed": qtype, "ok": False, "error": "a2a_resume_failed"}

    if qtype == "intake_gate" and intake_id and gate_id:
        from .intake.gates import on_intake_gate_approve, on_intake_gate_deny

        if decision == "approved":
            return {"routed": qtype, **on_intake_gate_approve(data_dir, intake_id, gate_id, body)}
        return {"routed": qtype, **on_intake_gate_deny(data_dir, intake_id, gate_id, body)}

    if task_id and gate_id:
        from .workflow.engine import on_gate_approve, on_gate_deny

        tr = TaskTracker(data_dir)
        task = tr.get(task_id)
        if not task:
            return {"routed": qtype, "error": "task_not_found"}
        if decision == "approved":
            result = on_gate_approve(data_dir, task, gate_id, body)
        else:
            result = on_gate_deny(data_dir, task, gate_id, body)
        if result.get("ok"):
            json_write(os.path.join(data_dir, "tasks", f"{task_id}.json"), task)
        return {"routed": qtype or "workflow_gate", **result}

    return outcome


def resolve_human_queue_item(
    data_dir: str,
    item_id: str,
    resolution: dict,
) -> tuple[Optional[dict], Dict[str, Any]]:
    """关闭 human-queue 项并执行副作用。返回 (item, side_effect)。"""
    pending = _find_pending_item(data_dir, item_id)
    if not pending:
        return None, {"error": "not_found"}

    item = close_item(data_dir, item_id, resolution)
    if not item:
        return None, {"error": "close_failed"}

    body = {
        "decision": resolution.get("decision"),
        "reviewer": resolution.get("reviewer"),
        "comment": resolution.get("comment"),
        "reason": resolution.get("reason"),
        "attachments": resolution.get("attachments"),
        "selected_copy_id": resolution.get("selected_copy_id"),
        "brief": resolution.get("brief"),
        "action": resolution.get("action"),
    }
    side = apply_human_queue_resolution(data_dir, pending, body)
    return item, side
