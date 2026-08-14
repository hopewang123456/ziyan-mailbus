"""人工待办队列 — store/human-queue.json SoT。"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from lib.infra.utils import _now_iso, file_lock, json_read, json_write
from lib.infra.clock import now_dt, now_iso, now_ts, now_utc_dt

_TZ_CN = timezone(timedelta(hours=8))
_VERSION = "1.0.0"


def queue_path(data_dir: str) -> str:
    return os.path.join(data_dir, "human-queue.json")


def _empty_doc() -> dict:
    return {"version": _VERSION, "updated_at": _now_iso(), "items": []}


def load_queue(data_dir: str) -> dict:
    path = queue_path(data_dir)
    if not os.path.isfile(path):
        return _empty_doc()
    doc = json_read(path, None)
    if not isinstance(doc, dict) or "items" not in doc:
        return _empty_doc()
    doc.setdefault("version", _VERSION)
    doc.setdefault("items", [])
    return doc


def save_queue(data_dir: str, doc: dict) -> None:
    doc["version"] = doc.get("version") or _VERSION
    doc["updated_at"] = _now_iso()
    path = queue_path(data_dir)
    os.makedirs(os.path.dirname(path) or data_dir, exist_ok=True)
    json_write(path, doc)


def _new_id() -> str:
    day = now_dt().strftime("%Y%m%d")
    return f"hq-{day}-{secrets.token_hex(3)}"


def _find_pending(doc: dict, *, task_id: str = "", gate_id: str = "", qtype: str = "") -> Optional[dict]:
    for item in doc.get("items") or []:
        if item.get("status") != "pending":
            continue
        if qtype and item.get("type") != qtype:
            continue
        if task_id and item.get("task_id") != task_id:
            continue
        if gate_id and item.get("gate_id") != gate_id:
            continue
        return item
    return None


def enqueue(data_dir: str, item: dict) -> str:
    """追加待办；task_id+gate_id 或 task_id+plan_approval 幂等。"""
    qtype = item.get("type", "")
    task_id = item.get("task_id", "")
    gate_id = item.get("gate_id", "")

    lock = file_lock(path=queue_path(data_dir))
    with lock:
        doc = load_queue(data_dir)
        if qtype == "plan_approval" and task_id:
            existing = _find_pending(doc, task_id=task_id, qtype="plan_approval")
            if existing:
                return existing["id"]
        if qtype == "workflow_gate" and task_id and gate_id:
            existing = _find_pending(doc, task_id=task_id, gate_id=gate_id, qtype="workflow_gate")
            if existing:
                return existing["id"]
        if qtype == "final_acceptance" and task_id:
            existing = _find_pending(doc, task_id=task_id, qtype="final_acceptance")
            if existing:
                return existing["id"]
        if qtype == "owner_confirmation" and task_id:
            existing = _find_pending(doc, task_id=task_id, qtype="owner_confirmation")
            if existing:
                return existing["id"]
        if qtype == "a2a_input_required" and task_id:
            ctx = item.get("context") or {}
            step_id = ctx.get("step_id") or ""
            for existing in doc.get("items") or []:
                if (
                    existing.get("status") == "pending"
                    and existing.get("type") == "a2a_input_required"
                    and existing.get("task_id") == task_id
                    and (existing.get("context") or {}).get("step_id") == step_id
                ):
                    return existing["id"]

        iid = item.get("id") or _new_id()
        now = _now_iso()
        entry = {
            "id": iid,
            "type": qtype,
            "status": item.get("status", "pending"),
            "created_at": item.get("created_at") or now,
            "title": item.get("title") or qtype,
        }
        for key in (
            "hint", "task_id", "intake_id", "workflow_id", "gate_id",
            "required_attachments_min", "require_brief", "require_select_field", "context",
        ):
            if key in item and item[key] is not None:
                entry[key] = item[key]
        doc.setdefault("items", []).append(entry)
        save_queue(data_dir, doc)
        return iid


def close_item(data_dir: str, item_id: str, resolution: dict) -> Optional[dict]:
    lock = file_lock(path=queue_path(data_dir))
    with lock:
        doc = load_queue(data_dir)
        for item in doc.get("items") or []:
            if item.get("id") != item_id:
                continue
            decision = (resolution.get("decision") or "approved").lower()
            item["status"] = "approved" if decision == "approved" else "denied"
            item["updated_at"] = _now_iso()
            item["resolution"] = {
                **{k: resolution[k] for k in (
                    "decision", "reviewer", "comment", "reason",
                    "attachments", "selected_copy_id", "brief",
                ) if k in resolution},
                "resolved_at": _now_iso(),
            }
            save_queue(data_dir, doc)
            return item
    return None


def close_by_task(data_dir: str, task_id: str, qtype: str, resolution: dict) -> Optional[dict]:
    doc = load_queue(data_dir)
    item = _find_pending(doc, task_id=task_id, qtype=qtype)
    if not item:
        return None
    return close_item(data_dir, item["id"], resolution)


def list_items(
    data_dir: str,
    *,
    status: str = "pending",
    qtype: str = "",
    task_id: str = "",
    intake_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, dict]:
    doc = load_queue(data_dir)
    items = list(doc.get("items") or [])
    if status and status != "all":
        items = [i for i in items if i.get("status") == status]
    if qtype:
        items = [i for i in items if i.get("type") == qtype]
    if task_id:
        items = [i for i in items if i.get("task_id") == task_id]
    if intake_id:
        items = [i for i in items if i.get("intake_id") == intake_id]
    total = len(items)
    page = items[offset: offset + limit]
    meta = {
        "version": doc.get("version", _VERSION),
        "updated_at": doc.get("updated_at"),
        "total": total,
    }
    return page, meta


def find_by_task_gate(data_dir: str, task_id: str, gate_id: str) -> Optional[dict]:
    doc = load_queue(data_dir)
    return _find_pending(doc, task_id=task_id, gate_id=gate_id, qtype="workflow_gate")


def enqueue_plan_approval(data_dir: str, task: dict) -> str:
    task_id = task.get("task_id") or task.get("id") or ""
    chain = task.get("chain") or []
    head = chain[0] if chain else {}
    planned = head.get("planned_role_types") or []
    return enqueue(data_dir, {
        "type": "plan_approval",
        "status": "pending",
        "title": f"批准任务计划 · {task_id[:32]}",
        "hint": f"planned_role_types: {planned}",
        "task_id": task_id,
        "context": {
            "intent": task.get("intent") or task.get("summary", ""),
            "tier": task.get("tier"),
            "task_type": task.get("task_type"),
            "planned_role_types": planned,
            "plan_meta": task.get("plan_meta"),
        },
    })


def _step_report_summary(step) -> str:
    """chain 末步 report 可能是 dict（含 summary）或 legacy 字符串。"""
    if not isinstance(step, dict):
        return ""
    report = step.get("report")
    if isinstance(report, dict):
        return str(report.get("summary") or "")
    if isinstance(report, str):
        return report
    return ""


def enqueue_final_acceptance(data_dir: str, task: dict) -> str:
    task_id = task.get("task_id") or task.get("id") or ""
    chain = task.get("chain") or []
    last = chain[-1] if chain else {}
    return enqueue(data_dir, {
        "type": "final_acceptance",
        "status": "pending",
        "title": f"终验 · {task_id[:32]}",
        "hint": task.get("intent") or task.get("summary", "")[:120],
        "task_id": task_id,
        "context": {
            "intent": task.get("intent") or task.get("summary", ""),
            "tier": task.get("tier"),
            "task_type": task.get("task_type"),
            "last_step_summary": _step_report_summary(last),
        },
    })
