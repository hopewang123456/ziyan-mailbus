"""审批上下文对外的仓储端口（由 adapters 实现）。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Self

from mailbus.core.approval.models import ApprovalItem
from mailbus.core.approval.values import ApprovalStatus
from mailbus.core.shared.ports import OutboxPort
from mailbus.core.workflow.ports import TaskRepository


class ApprovalRepository(Protocol):
    def add(self, item: ApprovalItem) -> None: ...

    def save(self, item: ApprovalItem) -> None: ...

    def get(self, approval_id: str) -> ApprovalItem | None: ...

    def list_all(
        self, status: ApprovalStatus | None = None, task_id: str | None = None
    ) -> list[ApprovalItem]: ...

    def due_pending(self, now: datetime) -> list[ApprovalItem]:
        """未裁决且已到期的审批；由派发器轮询。"""


class ApprovalUnitOfWork(Protocol):
    """审批用例的事务边界；阻塞档需要同事务更新任务。"""

    outbox: OutboxPort
    approvals: ApprovalRepository
    tasks: TaskRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
