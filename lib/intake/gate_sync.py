"""Intake 闸门状态同步到关联 pipeline task。"""

from __future__ import annotations

from ..tracker import TaskTracker
from ..utils import json_write


def sync_gate_to_task(data_dir: str, intake: dict, gate_id: str, resolution: dict) -> None:
    link = intake.get("pipeline_link") or {}
    tid = link.get("solution_task_id") or link.get("content_task_id") or link.get("intake_task_id")
    if not tid:
        return
    tr = TaskTracker(data_dir)
    task = tr.get(tid)
    if not task:
        return
    wf = task.setdefault("extensions", {}).setdefault("ziyan", {}).setdefault("workflow", {})
    gates = wf.setdefault("gates", [])
    inst = next((g for g in gates if g.get("gate_id") == gate_id), None)
    if not inst:
        inst = {"gate_id": gate_id}
        gates.append(inst)
    decision = (resolution.get("decision") or "approved").lower()
    inst["status"] = "approved" if decision == "approved" else "denied"
    if resolution.get("approved_at"):
        inst["approved_at"] = resolution["approved_at"]
    if resolution.get("reason"):
        inst["reason"] = resolution["reason"]
    json_write(tr._task_path(tid), task)
