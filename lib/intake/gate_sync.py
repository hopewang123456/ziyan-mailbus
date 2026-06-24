"""Intake gate → Task gate 同步。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..tracker import TaskTracker
from ..utils import json_write


def sync_gate_to_task(
    data_dir: str,
    intake: dict,
    gate_id: str,
    resolution: dict,
) -> Optional[dict]:
    link = intake.get("pipeline_link") or {}
    tid = link.get("solution_task_id") or link.get("intake_task_id")
    if not tid:
        return None
    tracker = TaskTracker(data_dir)
    task = tracker.get(tid)
    if not task:
        return None

    wf = (task.get("extensions") or {}).setdefault("ziyan", {}).setdefault("workflow", {})
    gates = wf.setdefault("gates", [])
    inst = next((g for g in gates if g.get("gate_id") == gate_id), None)
    if not inst:
        inst = {"gate_id": gate_id}
        gates.append(inst)
    decision = resolution.get("decision", "approved")
    inst["status"] = "approved" if decision == "approved" else "denied"
    if decision == "approved":
        inst["approved_by"] = resolution.get("reviewer") or "human"
        inst["approved_at"] = resolution.get("approved_at")
        inst["attachments"] = resolution.get("attachments") or []
        if resolution.get("brief"):
            inst["brief"] = resolution["brief"]
    else:
        inst["reason"] = resolution.get("reason", "")

    json_write(tracker._task_path(tid), task)
    return task


def copy_approved_intake_gates(intake: dict, task: dict) -> None:
    """spawn 后复制已批 intake gates 到 task。"""
    wf = (task.get("extensions") or {}).setdefault("ziyan", {}).setdefault("workflow", {})
    existing = {g.get("gate_id") for g in wf.get("gates") or []}
    for g in intake.get("commercial_gates") or []:
        if g.get("status") == "approved" and g.get("gate_id") not in existing:
            wf.setdefault("gates", []).append(dict(g))
