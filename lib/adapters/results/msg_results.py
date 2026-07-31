"""D1 msg-results store — ResultStorePort file adapter."""
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from lib.domain.types import StepRef, StepResult
from lib.harness.contract import write_d1_step_result
from lib.transport.step_result_io import read_step_result_file
from lib.adapters.results import ack as ack_mod


class FileResultStore:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def write_step_result(self, result: StepResult) -> str:
        path = write_d1_step_result(
            self.data_dir,
            result.step.task_id,
            result.step.step_id,
            {
                "agent_id": result.agent_id,
                "status": result.status,
                "attempt": result.step.attempt,
                **dict(result.payload),
            },
        )
        return path

    def read_step_result(self, step: StepRef) -> StepResult | None:
        raw = read_step_result_file(self.data_dir, step.task_id, step.step_id)
        if not raw:
            return None
        path = os.path.join(
            self.data_dir, "msg-results", step.task_id, f"step-{step.step_id}.json"
        )
        return StepResult(
            step=step,
            agent_id=str(raw.get("agent_id") or ""),
            status=str(raw.get("status") or raw.get("conclusion") or ""),
            path=path,
            payload=raw if isinstance(raw, Mapping) else {},
        )

    def list_unacked(self, agent_id: str, msg_ids: Sequence[str]) -> Sequence[str]:
        return ack_mod.list_unacked(self.data_dir, agent_id, list(msg_ids))

    def ack(self, agent_id: str, msg_ids: Sequence[str]) -> int:
        n = 0
        for mid in msg_ids:
            ack_mod.ack_message(self.data_dir, agent_id, mid)
            n += 1
        return n
