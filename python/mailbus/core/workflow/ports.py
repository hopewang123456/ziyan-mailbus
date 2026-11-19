"""流程上下文对外的仓储端口（由 adapters 实现）。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, Self

from mailbus.core.shared.ports import OutboxPort
from mailbus.core.workflow.models import (
    Task,
    TaskNode,
    WorkflowDef,
    WorkflowVersion,
)
from mailbus.core.workflow.values import TaskState


class WorkflowDefinitionRepository(Protocol):
    def add(self, definition: WorkflowDef) -> None: ...

    def save(self, definition: WorkflowDef) -> None:
        """更新名称与版本指针。"""

    def get(self, workflow_id: str) -> WorkflowDef | None: ...

    def list_all(self) -> list[WorkflowDef]: ...

    def delete(self, workflow_id: str) -> None: ...


class WorkflowVersionRepository(Protocol):
    def add(self, version: WorkflowVersion) -> None: ...

    def save(self, version: WorkflowVersion) -> None:
        """发布迁移；已发布版本视为不可变，重复保存无效。"""

    def get(self, workflow_id: str, version: int) -> WorkflowVersion | None: ...

    def list_by_workflow(self, workflow_id: str) -> list[WorkflowVersion]: ...

    def delete_by_workflow(self, workflow_id: str) -> None: ...


class TaskRepository(Protocol):
    def add(self, task: Task, nodes: Sequence[TaskNode]) -> None: ...

    def save(self, task: Task, nodes: Sequence[TaskNode]) -> None:
        """整任务保存：任务行与节点行同事务写入。"""

    def get(self, task_id: str) -> Task | None: ...

    def nodes(self, task_id: str) -> list[TaskNode]: ...

    def list_all(
        self, state: TaskState | None = None, owner_id: str | None = None
    ) -> list[Task]: ...


class WorkflowUnitOfWork(Protocol):
    """流程用例的事务边界；一个用例一个实例。"""

    outbox: OutboxPort
    definitions: WorkflowDefinitionRepository
    versions: WorkflowVersionRepository
    tasks: TaskRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
