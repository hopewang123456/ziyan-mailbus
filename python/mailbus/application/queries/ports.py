"""只读模型所需的仓储组合端口（不引入新聚合）。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.agents.ports import AgentRepository
from mailbus.core.approval.ports import ApprovalRepository
from mailbus.core.identity.ports import EmployeeRepository
from mailbus.core.messaging.ports import MessageRepository
from mailbus.core.org.ports import PositionRepository, TeamRepository
from mailbus.core.shared.ports import OutboxPort
from mailbus.core.skills.ports import SkillPackageRepository
from mailbus.core.workflow.ports import (
    TaskRepository,
    WorkflowDefinitionRepository,
)


class ReadUnitOfWork(Protocol):
    """overview / log 共用的事务范围；只读，不提交。"""

    outbox: OutboxPort
    employees: EmployeeRepository
    teams: TeamRepository
    positions: PositionRepository
    tasks: TaskRepository
    approvals: ApprovalRepository
    messages: MessageRepository
    agents: AgentRepository
    packages: SkillPackageRepository
    definitions: WorkflowDefinitionRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
