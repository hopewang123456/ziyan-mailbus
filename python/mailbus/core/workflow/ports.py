"""流程上下文对外的仓储端口（由 adapters 实现）。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, Self

from mailbus.core.shared.ports import OutboxPort
from mailbus.core.workflow.models import (
    Task,
    TaskArtifact,
    TaskEscalation,
    TaskNode,
    TaskRun,
    TaskVariable,
    WorkflowDef,
    WorkflowEdge,
    WorkflowNode,
    WorkflowVersion,
)
from mailbus.core.workflow.values import TaskState


class WorkflowDefinitionRepository(Protocol):
    def add(self, definition: WorkflowDef) -> None: ...

    def save(self, definition: WorkflowDef) -> None:
        """更新名称与版本指针。"""

    def get(self, workflow_id: str) -> WorkflowDef | None: ...

    def list_all(
        self, limit: int | None = None, offset: int = 0
    ) -> list[WorkflowDef]:
        """默认过滤软删除记录。"""

    def count(self) -> int: ...

    def soft_delete(
        self, workflow_id: str, deleted_at: datetime, deleted_by: str | None
    ) -> None: ...

    def delete(self, workflow_id: str) -> None: ...


class WorkflowVersionRepository(Protocol):
    def add(self, version: WorkflowVersion) -> None: ...

    def save(self, version: WorkflowVersion) -> None:
        """发布迁移；已发布版本视为不可变，重复保存无效。"""

    def get(self, workflow_id: str, version: int) -> WorkflowVersion | None: ...

    def list_by_workflow(
        self, workflow_id: str, limit: int | None = None, offset: int = 0
    ) -> list[WorkflowVersion]: ...

    def count_by_workflow(self, workflow_id: str) -> int: ...

    def delete_by_workflow(self, workflow_id: str) -> None: ...


class WorkflowGraphRepository(Protocol):
    """Graph 的唯一读写落点：wf_nodes + wf_node_transitions。"""

    def load(
        self, workflow_id: str, version: int
    ) -> tuple[list[WorkflowNode], list[WorkflowEdge]]: ...

    def replace(
        self,
        workflow_id: str,
        version: int,
        nodes: Sequence[WorkflowNode],
        edges: Sequence[WorkflowEdge],
    ) -> None:
        """整版本覆盖写入；调用方负责乐观锁判定。"""

    def copy(
        self, workflow_id: str, source_version: int, target_version: int
    ) -> None: ...

    def bump_revision(self, workflow_id: str, version: int) -> int:
        """revision + 1 并返回新值。"""


class TaskRepository(Protocol):
    def add(self, task: Task, nodes: Sequence[TaskNode]) -> None: ...

    def save(self, task: Task, nodes: Sequence[TaskNode]) -> None:
        """整任务保存：任务行与节点行同事务写入。"""

    def save_task(self, task: Task) -> None:
        """只写任务行（状态/负责人/终止原因/循环计数）。"""

    def save_node(self, node: TaskNode) -> None:
        """只写单个节点行（状态与当前 run 指针）。"""

    def get(self, task_id: str) -> Task | None: ...

    def get_node(self, task_id: str, node_id: str) -> TaskNode | None: ...

    def nodes(self, task_id: str) -> list[TaskNode]: ...

    def list_all(
        self,
        state: TaskState | None = None,
        owner_id: str | None = None,
        workflow_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        viewer_id: str | None = None,
    ) -> list[Task]: ...

    def count(
        self,
        state: TaskState | None = None,
        owner_id: str | None = None,
        workflow_id: str | None = None,
        viewer_id: str | None = None,
    ) -> int: ...

    def soft_delete(self, task_id: str, deleted_at: datetime, deleted_by: str | None) -> None: ...


class TaskRunRepository(Protocol):
    def add(self, run: TaskRun) -> None: ...

    def save(self, run: TaskRun) -> None:
        """更新状态、执行人、结果与时间戳。"""

    def get(self, run_id: str) -> TaskRun | None: ...

    def list_by_task(self, task_id: str) -> list[TaskRun]: ...

    def list_by_node(self, task_id: str, node_id: str) -> list[TaskRun]: ...

    def latest(self, task_id: str, node_id: str, fanout_slot: int = 0) -> TaskRun | None: ...

    def max_attempt(self, task_id: str, node_id: str) -> int: ...

    def claim(
        self, run_id: str, employee_id: str, started_at: datetime
    ) -> bool:
        """CAS：仅当仍为未认领的共享人工待办时成功。"""

    def count_active_by_employee(self, employee_id: str) -> int: ...

    def list_overdue(self, now: datetime, limit: int = 100) -> list[TaskRun]:
        """未到终态且已超过 deadline 的执行实例；由派发器轮询升级。"""


class TaskArtifactRepository(Protocol):
    def add(self, artifact: TaskArtifact) -> None: ...

    def get(self, artifact_id: str) -> TaskArtifact | None: ...

    def list_by_task(self, task_id: str) -> list[TaskArtifact]: ...

    def delete_for_node_except(
        self, task_id: str, node_id: str, keep_run_id: str
    ) -> None:
        """打回/重试时删除旧产物；扇出场景调用方不调用。"""


class TaskEscalationRepository(Protocol):
    def add(self, escalation: TaskEscalation) -> None: ...

    def list_by_task(self, task_id: str) -> list[TaskEscalation]: ...

    def has_open(self, task_id: str, reason: str) -> bool: ...


class TaskVariableRepository(Protocol):
    def add_many(self, variables: Sequence[TaskVariable]) -> None: ...

    def list_by_task(self, task_id: str) -> list[TaskVariable]: ...

    def upsert(self, variable: TaskVariable) -> None: ...


class WorkflowUnitOfWork(Protocol):
    """流程用例的事务边界；一个用例一个实例。"""

    outbox: OutboxPort
    definitions: WorkflowDefinitionRepository
    versions: WorkflowVersionRepository
    graphs: WorkflowGraphRepository
    tasks: TaskRepository
    runs: TaskRunRepository
    artifacts: TaskArtifactRepository
    escalations: TaskEscalationRepository
    variables: TaskVariableRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...

