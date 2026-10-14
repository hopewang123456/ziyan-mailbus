"""Fake AgentRuntimePort — records calls, never spawns a real CLI."""
from __future__ import annotations

from lib.domain.types import AgentRef, HealthStatus, ProbeResult, SpawnHandle
from lib.application.harness.contract import HarnessContract


class FakeRuntime:
    def __init__(self) -> None:
        self.probes: list[str] = []
        self.health_checks: list[str] = []
        self.spawns: list[dict] = []
        self.probe_ok: bool = True
        self.health_state: str = "up"
        self.default_timeout: int = 30

    def probe(self, agent: AgentRef) -> ProbeResult:
        self.probes.append(agent.agent_id)
        return ProbeResult(
            ok=self.probe_ok,
            agent_id=agent.agent_id,
            detail="fake",
            latency_ms=0,
        )

    def health(self, agent: AgentRef) -> HealthStatus:
        self.health_checks.append(agent.agent_id)
        return HealthStatus(
            agent_id=agent.agent_id,
            state=self.health_state,
            detail="fake",
        )

    def spawn(
        self,
        agent: AgentRef,
        contract: HarnessContract,
        *,
        argv_extra: tuple[str, ...] = (),
        timeout_seconds: int = 300,
    ) -> SpawnHandle:
        self.spawns.append(
            {
                "agent_id": agent.agent_id,
                "msg_id": contract.msg_id,
                "task_id": contract.task_id,
                "step_id": contract.step_id,
                "argv_extra": argv_extra,
                "timeout_seconds": timeout_seconds,
            }
        )
        return SpawnHandle(
            agent_id=agent.agent_id,
            session_id=f"fake-{agent.agent_id}-{len(self.spawns)}",
            pid=None,
            msg_id=contract.msg_id,
        )

    def push_timeout_seconds(self, agent: AgentRef, *, pipeline: bool = False) -> int:
        return self.default_timeout
