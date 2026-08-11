"""HumanGatePort adapter over lib.human_queue* (D10 · Protocol 已挂，厚逻辑仍原模块)."""
from __future__ import annotations

from typing import Any, Mapping

from lib.adapters.orchestration.human_queue import close_by_task as hq_close_by_task
from lib.adapters.orchestration.human_queue import close_item as hq_close_item
from lib.adapters.orchestration.human_queue import enqueue as hq_enqueue
from lib.adapters.orchestration.human_queue import enqueue_final_acceptance as hq_enqueue_final
from lib.adapters.orchestration.human_queue import enqueue_plan_approval as hq_enqueue_plan
from lib.adapters.orchestration.human_queue import find_by_task_gate as hq_find_gate
from lib.adapters.orchestration.human_queue import list_items as hq_list_items
from lib.adapters.orchestration.human_queue import load_queue as hq_load
from lib.application.orchestration.human_queue_resolve import resolve_human_queue_item
from lib.interfaces.gates import AuditPort


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

    def list_items(
        self,
        *,
        status: str = "pending",
        qtype: str = "",
        task_id: str = "",
        intake_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list, dict]:
        return hq_list_items(
            self._data_dir,
            status=status,
            qtype=qtype,
            task_id=task_id,
            intake_id=intake_id,
            limit=limit,
            offset=offset,
        )

    def close_item(self, item_id: str, resolution: Mapping[str, Any]) -> dict | None:
        return hq_close_item(self._data_dir, item_id, dict(resolution))

    def close_by_task(
        self, task_id: str, qtype: str, resolution: Mapping[str, Any],
    ) -> dict | None:
        return hq_close_by_task(self._data_dir, task_id, qtype, dict(resolution))

    def find_by_task_gate(self, task_id: str, gate_id: str) -> dict | None:
        return hq_find_gate(self._data_dir, task_id, gate_id)

    def enqueue_plan_approval(self, task: Mapping[str, Any]) -> str:
        return hq_enqueue_plan(self._data_dir, dict(task))

    def enqueue_final_acceptance(self, task: Mapping[str, Any]) -> str:
        return hq_enqueue_final(self._data_dir, dict(task))
