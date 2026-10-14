"""In-memory ResultStorePort — no filesystem / CLI."""
from __future__ import annotations

from typing import Sequence

from lib.domain.types import StepRef, StepResult


class FakeResultStore:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str, int], StepResult] = {}
        self._acked: set[tuple[str, str]] = set()

    def write_step_result(self, result: StepResult) -> str:
        key = (result.step.task_id, result.step.step_id, result.step.attempt)
        path = result.path or f"memory://{result.step.task_id}/step-{result.step.step_id}"
        stored = StepResult(
            step=result.step,
            agent_id=result.agent_id,
            status=result.status,
            path=path,
            payload=dict(result.payload),
        )
        self._by_key[key] = stored
        return path

    def read_step_result(self, step: StepRef) -> StepResult | None:
        return self._by_key.get((step.task_id, step.step_id, step.attempt))

    def list_unacked(self, agent_id: str, msg_ids: Sequence[str]) -> Sequence[str]:
        return [m for m in msg_ids if (agent_id, m) not in self._acked]

    def ack(self, agent_id: str, msg_ids: Sequence[str]) -> int:
        n = 0
        for mid in msg_ids:
            key = (agent_id, mid)
            if key not in self._acked:
                self._acked.add(key)
                n += 1
        return n
