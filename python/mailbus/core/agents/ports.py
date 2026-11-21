"""Agent 台账对外的仓储与目录端口（由 adapters 实现）。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.agents.models import Agent, AgentSummary
from mailbus.core.identity.ports import EmployeeRepository
from mailbus.core.shared.ports import OutboxPort


class AgentRepository(Protocol):
    def get(self, agent_id: str) -> Agent | None: ...

    def save(self, agent: Agent) -> None: ...

    def list_all(self) -> list[Agent]: ...

    def delete(self, agent_id: str) -> None: ...


class AgentDirectoryPort(Protocol):
    """只读摘要查询：员工视图与布局投影使用。"""

    def summaries(self, agent_ids: tuple[str, ...]) -> dict[str, AgentSummary]: ...


class AgentsUnitOfWork(Protocol):
    """Agent 用例的事务边界；员工仓储用于绑定与解绑。"""

    outbox: OutboxPort
    agents: AgentRepository
    employees: EmployeeRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
