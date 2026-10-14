from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from lib.domain.types import AgentRef


@runtime_checkable
class ConfigRepository(Protocol):
    def get_raw(self) -> Mapping[str, Any]: ...

    def get_agent(self, agent_id: str) -> AgentRef | None: ...

    def list_agents(self) -> Sequence[AgentRef]: ...

    def update(self, mutator: Callable[[dict[str, Any]], None]) -> None: ...

    def agent_config_mtime(self, agent_id: str) -> float | None: ...
