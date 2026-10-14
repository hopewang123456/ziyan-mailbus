"""order-intake.json 读写（商前 intake SoT）。"""

from __future__ import annotations

import os

from lib.infra.utils import file_lock, json_read, json_write


def _intake_path(data_dir: str) -> str:
    return os.path.join(data_dir, "leads", "order-intake.json")


def load_all(data_dir: str) -> list:
    items = json_read(_intake_path(data_dir), [])
    return items if isinstance(items, list) else []


def get(data_dir: str, intake_id: str) -> dict | None:
    for item in load_all(data_dir):
        if item.get("intake_id") == intake_id:
            return item
    return None


def upsert(data_dir: str, intake: dict) -> None:
    path = _intake_path(data_dir)
    iid = intake.get("intake_id", "")
    if not iid:
        raise ValueError("intake_id required")
    with file_lock(path=path):
        items = load_all(data_dir)
        for i, item in enumerate(items):
            if item.get("intake_id") == iid:
                items[i] = intake
                break
        else:
            items.append(intake)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json_write(path, items)


def ensure_gate(intake: dict, gate_id: str) -> dict:
    gates = intake.setdefault("commercial_gates", [])
    for g in gates:
        if g.get("gate_id") == gate_id:
            return g
    inst = {"gate_id": gate_id, "status": "pending"}
    gates.append(inst)
    return inst
