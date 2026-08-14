"""Intake 商前闸门 approve/deny。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from lib.composition import get_human_gate
from lib.infra.utils import _now_iso
from lib.application.orchestration.tracker import TaskTracker
from lib.application.workflow.engine import on_gate_approve as task_gate_approve
from lib.application.workflow.gate_validator import validate_approve, validate_deny
from lib.application.workflow.registry import get_gate_def, get_workflow, load_registry
from .gate_sync import sync_gate_to_task
from .spawn_rules import spawn_on_gate_approved
from .store import ensure_gate, get, upsert


def _gate(data_dir: str):
    return get_human_gate(data_dir)


def _resolve_gate_def(gate_id: str, registry: dict) -> Optional[dict]:
    for wf in (registry.get("workflows") or {}).values():
        g = get_gate_def(wf, gate_id)
        if g:
            return g
    return None


def _enqueue_intake_gate(data_dir: str, intake: dict, gate_id: str, gate_def: dict) -> str:
    return _gate(data_dir).enqueue({
        "type": "intake_gate",
        "status": "pending",
        "title": (gate_def.get("display") or {}).get("zh") or gate_id,
        "intake_id": intake.get("intake_id"),
        "gate_id": gate_id,
        "required_attachments_min": gate_def.get("required_attachments_min", 0),
        "context": {
            "title": intake.get("title"),
            "decision": intake.get("decision"),
            "stage": intake.get("stage"),
        },
    })


def on_intake_gate_approve(
    data_dir: str,
    intake_id: str,
    gate_id: str,
    body: dict,
) -> Dict[str, Any]:
    intake = get(data_dir, intake_id)
    if not intake:
        return {"ok": False, "error": "not_found", "http": 404}

    registry = load_registry(data_dir)
    gate_def = _resolve_gate_def(gate_id, registry)
    if not gate_def:
        return {"ok": False, "error": "not_found", "http": 404}

    inst = ensure_gate(intake, gate_id)
    if inst.get("status") == "approved":
        return {"ok": False, "error": "gate_not_pending", "http": 400}

    link = intake.get("pipeline_link") or {}
    if link.get("solution_task_id") and gate_id in ("customer_design_ok", "start_delivery"):
        task = TaskTracker(data_dir).get(link["solution_task_id"])
        if task:
            outcome = task_gate_approve(data_dir, task, gate_id, body)
            if outcome.get("ok"):
                sync_gate_to_task(data_dir, intake, gate_id, outcome.get("resolution", {}))
                inst.update({"status": "approved", "approved_by": body.get("reviewer") or "human", "approved_at": _now_iso()})
                upsert(data_dir, intake)
            return {**outcome, "intake": intake, "delegated": "task"}
        return {"ok": False, "error": "not_found", "http": 404}

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
        inst["brief"] = body["brief"]
        if gate_def.get("brief_field") == "requirements_brief":
            intake["requirements_brief"] = body["brief"]

    inst.update({
        "status": "approved",
        "approved_by": resolution["reviewer"],
        "approved_at": now,
        "attachments": resolution["attachments"],
    })

    actions: List[dict] = []
    spawned_task_id = None

    if gate_id == "contact_done":
        intake["stage"] = intake.get("stage") or "qualified"
        actions.append({"action": "set_stage", "stage": intake["stage"]})
    elif gate_id == "req_to_solution":
        try:
            spawn = spawn_on_gate_approved(data_dir, intake, gate_id, brief=body.get("brief") or "")
            spawned_task_id = spawn.get("spawned_task_id") if spawn else None
            actions.append({"action": "spawn_commercial_solution", "task_id": spawned_task_id})
        except Exception as exc:
            code = getattr(exc, "code", "spawn_failed")
            return {"ok": False, "error": code, "message": str(exc), "http": 409}
    elif gate_id == "content_start":
        try:
            spawn = spawn_on_gate_approved(data_dir, intake, gate_id)
            spawned_task_id = spawn.get("spawned_task_id") if spawn else None
            actions.append({"action": "spawn_video_publish", "task_id": spawned_task_id})
        except Exception as exc:
            code = getattr(exc, "code", "spawn_failed")
            return {"ok": False, "error": code, "message": str(exc), "http": 409}
    elif gate_id == "start_delivery":
        from lib.infra.org_defaults import org_default
        from lib.composition import get_ops

        finance_agent = org_default(data_dir, "finance_followup")
        title = intake.get("title") or intake_id
        get_ops().append_inbox_task(
            data_dir,
            finance_agent,
            f"🧾 商单进入交付 — {title}\n"
            f"intake_id: {intake_id}\n"
            f"请建立账期/回款提醒（store/billing/）。",
            priority="normal",
        )
        actions.append({"action": "notify_finance_followup"})

    on_ap = gate_def.get("on_approve") or {}
    if on_ap.get("set_stage"):
        intake["stage"] = on_ap["set_stage"]

    upsert(data_dir, intake)
    sync_gate_to_task(data_dir, intake, gate_id, resolution)

    hq = _gate(data_dir)
    for item in hq.load_queue().get("items") or []:
        if item.get("intake_id") == intake_id and item.get("gate_id") == gate_id and item.get("status") == "pending":
            hq.close_item(item["id"], resolution)
            break

    return {
        "ok": True,
        "gate_id": gate_id,
        "resolution": resolution,
        "intake": intake,
        "actions": actions,
        "spawned_task_id": spawned_task_id,
    }


def on_intake_gate_deny(
    data_dir: str,
    intake_id: str,
    gate_id: str,
    body: dict,
) -> Dict[str, Any]:
    intake = get(data_dir, intake_id)
    if not intake:
        return {"ok": False, "error": "not_found", "http": 404}

    val_errs = validate_deny(body)
    if val_errs:
        return {"ok": False, "error": val_errs[0], "http": 400}

    inst = ensure_gate(intake, gate_id)
    inst["status"] = "denied"
    inst["reason"] = body.get("reason", "")

    registry = load_registry(data_dir)
    gate_def = _resolve_gate_def(gate_id, registry) or {}
    on_den = gate_def.get("on_deny") or {}
    if on_den.get("action") == "close_intake":
        intake["decision"] = "reject"
        intake["stage"] = "closed"

    upsert(data_dir, intake)
    resolution = {"decision": "denied", "reviewer": body.get("reviewer") or "human", "reason": body.get("reason", "")}
    sync_gate_to_task(data_dir, intake, gate_id, resolution)
    return {"ok": True, "gate_id": gate_id, "resolution": resolution, "intake": intake}
