"""Workflow Engine — bind · step complete · gate approve/deny。"""

from __future__ import annotations

import os

from typing import Any, Dict, List, Optional

from ..human_queue import close_by_task, enqueue, find_by_task_gate
from ..pipeline_step import planned_agents_remaining, planned_role_types_remaining
from ..task_fsm import TaskFsmState, ensure_fsm, get_active_step
from ..utils import _now_iso, json_write
from .gate_validator import validate_approve, validate_deny
from .phase_append import append_phase_steps, append_single_role_type, spawn_phase_chain
from .registry import (
    find_phase,
    get_gate_def,
    get_workflow,
    initial_phase_id,
    load_registry,
    resolve_workflow_id,
)


def workflow_ext(task: dict) -> dict:
    ext = task.setdefault("extensions", {})
    ziyan = ext.setdefault("ziyan", {})
    if "workflow" not in ziyan:
        ziyan["workflow"] = {}
    return ziyan["workflow"]


def bind_workflow(task: dict, envelope: dict, *, data_dir: str) -> None:
    registry = load_registry(data_dir)
    tt = (task.get("task_type") or envelope.get("task_type") or "unknown").lower()
    ext_in = envelope.get("extensions") or {}
    wf_id = resolve_workflow_id(tt, ext_in, registry)
    wf = get_workflow(registry, wf_id) or {}
    wf_e = workflow_ext(task)
    incoming = (ext_in.get("ziyan.workflow") or {})
    wf_e.update({
        "workflow_id": wf_id,
        "version": incoming.get("version") or wf.get("version", "1.0.0"),
        "phase": incoming.get("phase") or initial_phase_id(wf),
        "gates": list(incoming.get("gates") or []),
    })


def _gate_inst(task: dict, gate_id: str) -> Optional[dict]:
    for g in workflow_ext(task).get("gates") or []:
        if g.get("gate_id") == gate_id:
            return g
    return None


def _ensure_gate_pending(task: dict, gate_id: str) -> dict:
    inst = _gate_inst(task, gate_id)
    if not inst:
        inst = {"gate_id": gate_id, "status": "pending"}
        workflow_ext(task).setdefault("gates", []).append(inst)
    elif inst.get("status") not in ("approved", "denied"):
        inst["status"] = "pending"
    return inst


def _block_for_gate(task: dict, gate_id: str) -> None:
    ensure_fsm(task)
    task["fsm"]["state"] = TaskFsmState.BLOCKED.value
    task["fsm"]["substate"] = "await_gate"
    task["fsm"]["gate_id"] = gate_id
    task["status"] = "running"
    _ensure_gate_pending(task, gate_id)


def _enqueue_gate(data_dir: str, task: dict, gate_id: str, wf: dict, *, qtype: str = "workflow_gate") -> str:
    gate_def = get_gate_def(wf, gate_id) or {}
    tid = task.get("task_id") or ""
    title = gate_def.get("display", {}).get("zh") or gate_id
    ctx = {
        "intent": task.get("intent"),
        "tier": task.get("tier"),
        "task_type": task.get("task_type"),
    }
    if qtype == "llm_step_confirm":
        llm = (task.get("extensions") or {}).get("ziyan", {}).get("llm_route") or {}
        ctx["llm_suggestion"] = llm.get("suggested_step")
        ctx["llm_rationale"] = llm.get("rationale", "")
        ctx["rag_citations"] = llm.get("rag_citations") or []
    return enqueue(data_dir, {
        "type": qtype,
        "status": "pending",
        "title": title,
        "hint": task.get("intent") or task.get("summary", "")[:120],
        "task_id": tid,
        "workflow_id": wf.get("id"),
        "gate_id": gate_id,
        "required_attachments_min": gate_def.get("required_attachments_min", 0),
        "require_select_field": gate_def.get("require_select_field"),
        "context": ctx,
    })


def maybe_block_after_step(
    task: dict,
    step: dict,
    result: dict,
    *,
    data_dir: str,
) -> Optional[dict]:
    """步骤完成后：fixed_phases after_agent gate 或 llm_adaptive route。"""
    registry = load_registry(data_dir)
    wf_e = workflow_ext(task)
    wf_id = wf_e.get("workflow_id")
    if not wf_id:
        return None
    wf = get_workflow(registry, wf_id)
    if not wf:
        return None

    chain = task.get("chain") or []
    if planned_role_types_remaining(chain) or planned_agents_remaining(chain):
        return None

    mode = wf.get("mode") or "fixed_phases"

    if mode == "fixed_phases":
        phase = find_phase(wf, wf_e.get("phase") or "")
        after = (phase or {}).get("after_agent") or {}
        gate_id = after.get("gate_id")

        executed = set(wf_e.get("tools_executed") or [])
        for step in (phase or {}).get("steps") or []:
            if step.get("node_type") != "tool":
                continue
            tid = step.get("tool_id")
            if tid and tid not in executed:
                from .tool_exec import run_tool_step, tool_live_enabled
                live = tool_live_enabled(data_dir, task)
                run_tool_step(data_dir, task, tid, dry_run=not live)
                if not gate_id:
                    return None
                break

        if not gate_id:
            return None
        inst = _gate_inst(task, gate_id)
        if inst and inst.get("status") == "approved":
            return None
        _block_for_gate(task, gate_id)
        hq_id = _enqueue_gate(data_dir, task, gate_id, wf)
        task["fsm"]["human_queue_id"] = hq_id
        return {"gate_id": gate_id, "human_queue_id": hq_id, "action": "gate_blocked"}

    if mode == "llm_adaptive":
        policy = wf.get("llm_policy") or {}
        max_routes = int(policy.get("max_llm_routes_per_task") or 12)
        llm_ext = (task.get("extensions") or {}).get("ziyan", {}).get("llm_route") or {}
        if int(llm_ext.get("route_count") or 0) >= max_routes:
            return None
        from .llm_route import route_next_step

        route = route_next_step(task, data_dir=data_dir)
        task.setdefault("extensions", {}).setdefault("ziyan", {})["llm_route"] = {
            "pending_confirm": True,
            "suggested_step": route.get("suggested_step"),
            "rationale": route.get("rationale", ""),
            "rag_citations": route.get("rag_citations", []),
            "routed_at": _now_iso(),
            "route_count": int(llm_ext.get("route_count") or 0) + 1,
        }
        gate_id = policy.get("confirm_gate_id") or "llm_step_confirm"
        _block_for_gate(task, gate_id)
        hq_id = _enqueue_gate(data_dir, task, gate_id, wf, qtype="llm_step_confirm")
        task["fsm"]["human_queue_id"] = hq_id
        return {"gate_id": gate_id, "human_queue_id": hq_id, "action": "llm_route"}

    return None


def on_gate_approve(
    data_dir: str,
    task: dict,
    gate_id: str,
    body: dict,
) -> Dict[str, Any]:
    registry = load_registry(data_dir)
    wf_e = workflow_ext(task)
    wf = get_workflow(registry, wf_e.get("workflow_id") or "")
    if not wf:
        return {"ok": False, "error": "not_found", "http": 404}

    gate_def = get_gate_def(wf, gate_id)
    if not gate_def:
        return {"ok": False, "error": "not_found", "http": 404}

    inst = _gate_inst(task, gate_id)
    if inst and inst.get("status") == "approved":
        return {"ok": False, "error": "gate_not_pending", "http": 400}

    fsm = task.get("fsm") or {}
    if fsm.get("gate_id") and fsm.get("gate_id") != gate_id:
        if inst and inst.get("status") != "pending":
            return {"ok": False, "error": "task_fsm_conflict", "http": 409}

    val_errs = validate_approve(body, gate_def)
    if val_errs:
        return {"ok": False, "error": val_errs[0], "http": 400}

    now = _now_iso()
    resolution = {
        "decision": "approved",
        "reviewer": body.get("reviewer") or "human",
        "comment": body.get("comment", ""),
        "attachments": body.get("attachments") or [],
        "approved_at": now,
    }
    if body.get("brief"):
        resolution["brief"] = body["brief"]
    if body.get("selected_copy_id"):
        resolution["selected_copy_id"] = body["selected_copy_id"]

    from .tool_exec import mark_tool_live_after_gate, run_tool_step, tool_live_enabled
    mark_tool_live_after_gate(task, body, gate_def)

    inst = _ensure_gate_pending(task, gate_id)
    inst.update({
        "status": "approved",
        "approved_by": resolution["reviewer"],
        "approved_at": now,
        "attachments": resolution["attachments"],
        **({"brief": body["brief"]} if body.get("brief") else {}),
        **({"selected_copy_id": body["selected_copy_id"]} if body.get("selected_copy_id") else {}),
    })

    tid = task.get("task_id") or ""
    close_by_task(data_dir, tid, "workflow_gate", resolution)
    close_by_task(data_dir, tid, "llm_step_confirm", resolution)

    actions: List[dict] = []
    on_ap = gate_def.get("on_approve") or {}
    action = on_ap.get("action") or ""

    if gate_id == "llm_step_confirm" or action == "spawn_phase" and wf.get("mode") == "llm_adaptive":
        llm = (task.get("extensions") or {}).get("ziyan", {}).get("llm_route") or {}
        suggested = llm.get("suggested_step") or {}
        rt = suggested.get("role_type")
        if rt is not None:
            append_single_role_type(task, int(rt), pin_agent=suggested.get("agent_id") or "")
            actions.append({"action": "spawn_llm_step", "role_type": rt})
        llm["pending_confirm"] = False
    elif action == "append_phase":
        phase = find_phase(wf, on_ap.get("phase_id") or "")
        if phase:
            rts = append_phase_steps(task, phase)
            wf_e["phase"] = on_ap.get("phase_id")
            actions.append({"action": "append_phase", "phase_id": on_ap.get("phase_id"), "role_types": rts})
    elif action == "spawn_phase":
        phase = find_phase(wf, on_ap.get("phase_id") or "")
        if phase:
            spawn_phase_chain(task, phase, data_dir=data_dir)
            wf_e["phase"] = on_ap.get("phase_id")
            actions.append({"action": "spawn_phase", "phase_id": on_ap.get("phase_id")})
    elif action == "execute_tool":
        tool_id = on_ap.get("tool_id")
        if tool_id:
            live = tool_live_enabled(data_dir, task, gate_id=gate_id, body=body, gate_def=gate_def)
            result = run_tool_step(data_dir, task, tool_id, dry_run=not live)
            actions.append({"action": "execute_tool", "tool_id": tool_id, "live": live, "ok": result.get("ok")})

    if on_ap.get("set_stage"):
        wf_e["stage"] = on_ap["set_stage"]

    ensure_fsm(task)
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"].pop("substate", None)
    task["fsm"].pop("gate_id", None)
    task["fsm"].pop("human_queue_id", None)
    task["status"] = "running"

    dispatch_ok = False
    if action == "spawn_phase" and wf.get("mode") != "llm_adaptive":
        dispatch_ok = _dispatch_first_step(data_dir, task)
    else:
        dispatch_ok = _maybe_dispatch_next(data_dir, task)
    if dispatch_ok:
        actions.append({"action": "dispatch", "ok": True})

    return {
        "ok": True,
        "gate_id": gate_id,
        "resolution": resolution,
        "actions": actions,
        "dispatch_ok": dispatch_ok,
        "task": task,
    }


def on_gate_deny(
    data_dir: str,
    task: dict,
    gate_id: str,
    body: dict,
) -> Dict[str, Any]:
    registry = load_registry(data_dir)
    wf_e = workflow_ext(task)
    wf = get_workflow(registry, wf_e.get("workflow_id") or "")
    gate_def = get_gate_def(wf or {}, gate_id)
    if not wf or not gate_def:
        return {"ok": False, "error": "not_found", "http": 404}

    val_errs = validate_deny(body)
    if val_errs:
        return {"ok": False, "error": val_errs[0], "http": 400}

    inst = _ensure_gate_pending(task, gate_id)
    inst["status"] = "denied"
    inst["reason"] = body.get("reason", "")
    inst["denied_at"] = _now_iso()

    resolution = {
        "decision": "denied",
        "reviewer": body.get("reviewer") or "human",
        "reason": body.get("reason", ""),
        "comment": body.get("comment", ""),
    }
    tid = task.get("task_id") or ""
    close_by_task(data_dir, tid, "workflow_gate", resolution)
    close_by_task(data_dir, tid, "llm_step_confirm", resolution)

    actions: List[dict] = []
    on_den = gate_def.get("on_deny") or {}
    deny_action = on_den.get("action") or ""

    if deny_action == "rollback_phase":
        rb = on_den.get("rollback_phase_id")
        wf_e["phase"] = rb
        actions.append({"action": "rollback_phase", "rollback_phase_id": rb})
    elif deny_action == "replan_llm":
        ensure_fsm(task)
        ziyan = task.setdefault("extensions", {}).setdefault("ziyan", {})
        ziyan.pop("llm_route", None)
        actions.append({"action": "replan_llm"})
        from ..router.dispatch import start_executing
        from ..task_fsm import TaskFsmState

        task["fsm"]["state"] = TaskFsmState.EXECUTING.value
        task["fsm"].pop("substate", None)
        task["fsm"].pop("gate_id", None)
        task["status"] = "running"
        start_executing(task)
        actions.append({"action": "resume_executing"})

    if deny_action != "replan_llm":
        ensure_fsm(task)
        task["fsm"]["state"] = TaskFsmState.BLOCKED.value
        task["fsm"]["substate"] = "gate_denied"
        task["fsm"]["gate_id"] = gate_id

    return {
        "ok": True,
        "gate_id": gate_id,
        "resolution": resolution,
        "actions": actions,
        "task": task,
    }


def _dispatch_first_step(data_dir: str, task: dict) -> bool:
    from ..fsm_dispatch import dispatch_fsm_step
    from ..task_fsm import mark_step_dispatched

    chain = task.get("chain") or []
    if not chain:
        return False
    step = chain[0]
    tid = task.get("task_id") or ""
    ok = dispatch_fsm_step(data_dir, tid, step, summary=task.get("intent") or "")
    if ok:
        mark_step_dispatched(step)
        task["fsm"]["active_step_id"] = step.get("step_id")
        task["assignee"] = step.get("to_agent") or step.get("to_person") or ""
    return ok


def _maybe_dispatch_next(data_dir: str, task: dict) -> bool:
    """gate 批准后：若链上无 active 步或当前步已完成，dispatch 下一步。"""
    from ..fsm_dispatch import dispatch_fsm_step
    from ..task_fsm import mark_step_dispatched
    from ..pipeline_step import step_agent

    chain = task.get("chain") or []
    active = get_active_step(task)
    if active and active.get("fsm_state") not in ("completed", "skipped", "superseded"):
        if active.get("fsm_state") in ("pending", "queued", "dispatched", "awaiting_result", "in_progress"):
            if active.get("fsm_state") != "queued":
                return False

    head = chain[0] if chain else {}
    planned = list(head.get("planned_role_types") or [])
    if not planned:
        return False

    rt = planned.pop(0)
    head["planned_role_types"] = planned
    from ..dispatch.role_resolver import resolve_agent_for_role_type
    from ..dispatch.tier_filter import dispatch_action_from_envelope
    from ..locale.role_labels import role_type_to_zh
    from ..task_fsm import create_next_step
    from ..utils import json_read

    action = dispatch_action_from_envelope(task)
    agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}
    agent_id, _meta = resolve_agent_for_role_type(
        data_dir, int(rt), action=action, agents_cfg=agents_cfg,
    )
    role_zh = role_type_to_zh(int(rt), data_dir)
    prev = chain[-1] if chain else head
    nxt = create_next_step(
        task,
        to_role=role_zh,
        to_person=agent_id,
        from_role=prev.get("to_role", ""),
        from_person=step_agent(prev) or prev.get("to_agent", ""),
        role_type=int(rt),
    )
    chain.append(nxt)
    task["assignee"] = agent_id
    task["fsm"]["active_step_id"] = nxt["step_id"]
    tid = task.get("task_id") or ""
    ok = dispatch_fsm_step(data_dir, tid, nxt, summary=task.get("intent") or "")
    if ok:
        mark_step_dispatched(nxt)
    return ok
