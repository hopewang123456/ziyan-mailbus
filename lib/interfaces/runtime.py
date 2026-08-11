from __future__ import annotations

from typing import Protocol, runtime_checkable

from lib.domain.types import AgentRef, HealthStatus, ProbeResult, SpawnHandle
from lib.application.harness.contract import HarnessContract


@runtime_checkable
class AgentRuntimePort(Protocol):
    def probe(self, agent: AgentRef) -> ProbeResult: ...

    def health(self, agent: AgentRef) -> HealthStatus: ...

    def spawn(self, agent: AgentRef, contract: HarnessContract, *, argv_extra: tuple[str, ...] = (), timeout_seconds: int = 300) -> SpawnHandle: ...

    def push_timeout_seconds(self, agent: AgentRef, *, pipeline: bool = False) -> int: ...
