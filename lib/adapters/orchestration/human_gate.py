"""HumanGatePort adapter over lib.human_queue* (D10 · Protocol 已挂，厚逻辑仍原模块)."""
from __future__ import annotations

from typing import Any, Mapping

from lib.human_queue import enqueue as hq_enqueue
from lib.human_queue import load_queue as hq_load
from lib.human_queue_resolve import resolve_human_queue_item
from lib.ports.gates import AuditPort


class HumanGateAdapter:
    def __init__(self, data_dir: str, audit: AuditPort | None = None) -> None:
        self._data_dir = data_dir
        self._audit = audit

    def enqueue(self, item: Mapping[str, Any]) -> str:
        payload = dict(item)
        iid = hq_enqueue(self._data_dir, payload)
        if self._audit is not None:
            self._audit.append(
                "human_gate.enqueue",
                {
                    "id": iid,
                    "type": payload.get("type"),
                    "task_id": payload.get("task_id"),
                },
            )
        return iid

    def resolve(self, item_id: str, body: Mapping[str, Any]) -> dict:
        resolution = dict(body)
        item, side = resolve_human_queue_item(self._data_dir, item_id, resolution)
        if self._audit is not None:
            self._audit.append(
                "human_gate.resolve",
                {
                    "id": item_id,
                    "found": item is not None,
                    "decision": resolution.get("decision"),
                    "task_id": (item or {}).get("task_id") if item else None,
                },
            )
        return {"item": item, "side": side}

    def load_queue(self) -> dict:
        return hq_load(self._data_dir)
