"""FSM 人工口动作 — approve-plan · accept · accepting 流转。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from lib.application.orchestration.pipeline.step import step_role_type
from lib.composition import get_fsm, get_human_gate
from lib.domain.fsm import TaskFsmState
from lib.infra.utils import _now_iso, json_write


def _fsm():
    return get_fsm()


def _gate(data_dir: str):
    return get_human_gate(data_dir)


def _task_envelope(task: dict) -> dict:
    return {
        "protocol_version": task.get("protocol_version", "mailbus-a2a/1"),
        "task_id": task.get("task_id") or task.get("id"),
        "intent": task.get("intent") or task.get("summary", ""),
        "initiator": task.get("initiator", "human"),
        "mode": "auto",
        "tier": task.get("tier") or "M",
        "task_type": task.get("task_type") or "unknown",
        "constraints": task.get("constraints") or {},
    }


def enter_accepting_or_succeed(task: dict, result: dict, *, data_dir: str) -> str:
    """链走完：S+验收员自动终验，否则 entering accepting + human-queue。"""
    _fsm().ensure(task)
    tier = (task.get("tier") or "M").upper()
    conclusion = (result.get("conclusion") or "").lower()
    chain = task.get("chain") or []
    last_rt = step_role_type(chain[-1]) if chain else None

    if tier == "S" and last_rt == 12 and conclusion == "approved":
        _write_acceptance(
            data_dir, task,
            decision="approved",
            reviewer=result.get("agent") or chain[-1].get("to_agent") or "",
            method="auto",
            comment="S-tier auto acceptance (role_type=12, approved)",
        )
        task["fsm"]["state"] = TaskFsmState.SUCCEEDED.value
        task["status"] = "success"
        task["fsm"].pop("substate", None)
        task["fsm"].pop("human_queue_id", None)
        _fsm().append_history(task, "auto_accept", {"method": "auto"})
        return "auto_accept"

    task["fsm"]["state"] = TaskFsmState.ACCEPTING.value
    task["fsm"].pop("substate", None)
    task["status"] = "pending"
    hq_id = _gate(data_dir).enqueue_final_acceptance(task)
    task["fsm"]["human_queue_id"] = hq_id
    _fsm().append_history(task, "accepting", {"human_queue_id": hq_id})
    return "accepting"


def _write_acceptance(
    data_dir: str,
    task: dict,
    *,
    decision: str,
    reviewer: str,
    method: str = "manual",
    comment: str = "",
    reason: str = "",
    attachments: Optional[list] = None,
) -> str:
    tid = task.get("task_id") or task.get("id") or ""
    out_dir = _fsm().step_result_dir(data_dir, tid)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "acceptance.json")
    payload = {
        "task_id": tid,
        "decision": decision,
        "reviewer": reviewer,
        "method": method,
        "comment": comment,
        "reason": reason,
        "attachments": attachments or [],
        "timestamp": _now_iso(),
    }
    json_write(path, payload)
    task.setdefault("acceptance_record", payload)
    return path


def apply_approve_plan(task: dict, body: dict, *, data_dir: str) -> Dict[str, Any]:
    _fsm().ensure(task)
    fsm = task["fsm"]
    tid = task.get("task_id") or task.get("id") or ""

    if fsm.get("state") != TaskFsmState.CREATED.value:
        return {"ok": False, "error": "invalid_fsm_state"}
    if fsm.get("substate") != "await_plan_approval":
        return {"ok": False, "error": "invalid_fsm_state"}

    decision = (body.get("decision") or "").lower()
    reviewer = body.get("reviewer") or "human"
    resolution = {
        "decision": decision,
        "reviewer": reviewer,
        "comment": body.get("comment", ""),
        "reason": body.get("reason", ""),
    }

    if decision == "approved":
        from lib.application.orchestration.router.dispatch import dispatch_first_step, start_executing

        fsm.pop("substate", None)
        start_executing(task)
        dispatch_ok = dispatch_first_step(data_dir, task)
        _gate(data_dir).close_by_task(tid, "plan_approval", resolution)
        fsm.pop("human_queue_id", None)
        _fsm().append_history(task, "approve_plan", {"reviewer": reviewer, "dispatch_ok": dispatch_ok})
        return {"ok": True, "action": "approve_plan", "dispatch_ok": dispatch_ok, "task": task}

    if decision == "denied":
        reason = (body.get("reason") or "").strip()
        if not reason:
            return {"ok": False, "error": "missing_reason"}
        _gate(data_dir).close_by_task(tid, "plan_approval", resolution)
        action = body.get("action") or "replan"
        if action == "replan":
            from lib.application.orchestration.dispatch.role_resolver import resolve_agent_for_role_type
            from lib.application.orchestration.pipeline.chain import init_chain_from_planned
            from lib.application.orchestration.router.dispatch import set_await_plan_approval
            from lib.application.orchestration.router.planner import plan_replan

            envelope = _task_envelope(task)
            constraints = dict(envelope.get("constraints") or {})
            constraints["replan_reason"] = reason
            envelope["constraints"] = constraints
            out = plan_replan(envelope, data_dir=data_dir)
            pipeline_chain = init_chain_from_planned(
                out["planned_chain"],
                tid,
                resolve_agent=lambda rt, pin: resolve_agent_for_role_type(
                    data_dir, rt, pin_agent=pin,
                ),
            )
            task["chain"] = pipeline_chain
            task["plan_meta"] = out["plan_meta"]
            set_await_plan_approval(task)
            hq_id = _gate(data_dir).enqueue_plan_approval(task)
            task["fsm"]["human_queue_id"] = hq_id
            _fsm().append_history(task, "deny_replan", {"reason": reason, "human_queue_id": hq_id})
            return {"ok": True, "action": "deny_replan", "task": task}

        task["fsm"]["state"] = TaskFsmState.CANCELLED.value
        task["fsm"].pop("substate", None)
        task["status"] = "cancelled"
        task["error"] = {"reason": reason, "action": action}
        _fsm().append_history(task, "deny_cancel", {"reason": reason})
        return {"ok": True, "action": "deny_cancel", "task": task}

    return {"ok": False, "error": "invalid_decision"}


def apply_accept(task: dict, body: dict, *, data_dir: str) -> Dict[str, Any]:
    _fsm().ensure(task)
    fsm = task["fsm"]
    tid = task.get("task_id") or task.get("id") or ""

    if fsm.get("state") != TaskFsmState.ACCEPTING.value:
        return {"ok": False, "error": "invalid_fsm_state"}

    decision = (body.get("decision") or "").lower()
    reviewer = body.get("reviewer") or "human"
    attachments = body.get("attachments") or []

    if decision == "approved":
        _write_acceptance(
            data_dir, task,
            decision="approved",
            reviewer=reviewer,
            method="manual",
            comment=body.get("comment", ""),
            attachments=attachments,
        )
        fsm["state"] = TaskFsmState.SUCCEEDED.value
        task["status"] = "success"
        _gate(data_dir).close_by_task(tid, "final_acceptance", {
            "decision": "approved",
            "reviewer": reviewer,
            "comment": body.get("comment", ""),
            "attachments": attachments,
        })
        fsm.pop("human_queue_id", None)
        _fsm().append_history(task, "accept", {"reviewer": reviewer})
        return {"ok": True, "action": "accept", "task": task}

    if decision == "denied":
        reason = (body.get("reason") or "").strip()
        if not reason:
            return {"ok": False, "error": "missing_reason"}
        _write_acceptance(
            data_dir, task,
            decision="denied",
            reviewer=reviewer,
            method="manual",
            reason=reason,
            attachments=attachments,
        )
        _gate(data_dir).close_by_task(tid, "final_acceptance", {
            "decision": "denied",
            "reviewer": reviewer,
            "reason": reason,
            "attachments": attachments,
        })
        action = body.get("action") or "rollback"
        if action == "rollback":
            outcome = _fsm().apply_rollback(
                task,
                to_step=body.get("rollback_to_step"),
                to_person=body.get("target_agent") or body.get("to_agent"),
                reason=reason,
            )
            if not outcome.get("ok"):
                return outcome
            fsm.pop("human_queue_id", None)
            _fsm().append_history(task, "accept_deny_rollback", {"reason": reason})
            return {"ok": True, "action": "accept_deny_rollback", "task": task, "next_step": outcome.get("next_step")}

        fsm["state"] = TaskFsmState.BLOCKED.value
        task["status"] = "failed"
        task["error"] = {"reason": reason, "action": action}
        fsm.pop("human_queue_id", None)
        _fsm().append_history(task, "accept_deny", {"reason": reason})
        return {"ok": True, "action": "accept_deny", "task": task}

    return {"ok": False, "error": "invalid_decision"}
