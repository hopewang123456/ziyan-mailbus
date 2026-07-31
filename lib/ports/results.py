from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from lib.domain.types import StepRef, StepResult


@runtime_checkable
class ResultStorePort(Protocol):
    def write_step_result(self, result: StepResult) -> str: ...

    def read_step_result(self, step: StepRef) -> StepResult | None: ...

    def list_unacked(self, agent_id: str, msg_ids: Sequence[str]) -> Sequence[str]: ...

    def ack(self, agent_id: str, msg_ids: Sequence[str]) -> int: ...
