"""order-intake.json CRUD — store/leads/order-intake.json。"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from ..utils import _now_iso, file_lock, json_read, json_write


def intake_path(data_dir: str) -> str:
    return os.path.join(data_dir, "leads", "order-intake.json")


def load_all(data_dir: str) -> List[dict]:
    data = json_read(intake_path(data_dir), [])
    if isinstance(data, dict):
        return list(data.get("items") or [])
    return list(data) if isinstance(data, list) else []


def save_all(data_dir: str, items: List[dict]) -> None:
    os.makedirs(os.path.dirname(intake_path(data_dir)), exist_ok=True)
    json_write(intake_path(data_dir), items)


def get(data_dir: str, intake_id: str) -> Optional[dict]:
    for item in load_all(data_dir):
        if item.get("intake_id") == intake_id:
            return item
    return None


def upsert(data_dir: str, item: dict) -> dict:
    items = load_all(data_dir)
    iid = item.get("intake_id", "")
    lock = file_lock(path=intake_path(data_dir))
    with lock:
        items = load_all(data_dir)
        found = False
        for i, existing in enumerate(items):
            if existing.get("intake_id") == iid:
                item.setdefault("updated_at", _now_iso())
                items[i] = {**existing, **item}
                found = True
                break
        if not found:
            item.setdefault("created_at", _now_iso())
            item.setdefault("updated_at", _now_iso())
            items.append(item)
        save_all(data_dir, items)
    return get(data_dir, iid) or item


def _gate_inst(intake: dict, gate_id: str) -> Optional[dict]:
    for g in intake.get("commercial_gates") or []:
        if g.get("gate_id") == gate_id:
            return g
    return None


def ensure_gate(intake: dict, gate_id: str) -> dict:
    gates = intake.setdefault("commercial_gates", [])
    inst = _gate_inst(intake, gate_id)
    if not inst:
        inst = {"gate_id": gate_id, "status": "pending"}
        gates.append(inst)
    return inst


def pending_gates(intake: dict) -> List[str]:
    return [
        g["gate_id"] for g in (intake.get("commercial_gates") or [])
        if g.get("status") == "pending"
    ]


def list_summaries(
    data_dir: str,
    *,
    decision: str = "",
    stage: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[List[dict], int]:
    items = load_all(data_dir)
    if decision:
        items = [i for i in items if (i.get("decision") or "") == decision]
    if stage:
        items = [i for i in items if (i.get("stage") or "") == stage]
    total = len(items)
    page = items[offset: offset + limit]
    out = []
    for i in page:
        out.append({
            "intake_id": i.get("intake_id"),
            "title": i.get("title"),
            "score": i.get("score"),
            "decision": i.get("decision"),
            "stage": i.get("stage"),
            "pending_gates": pending_gates(i),
            "pipeline_link": i.get("pipeline_link") or {},
        })
    return out, total
