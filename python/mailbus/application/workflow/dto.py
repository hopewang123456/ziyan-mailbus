"""流程用例的输入/输出模型（application 内部 DTO）。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from mailbus.core.shared.errors import InvalidStateError
from mailbus.core.workflow.models import (
    Task,
    TaskNode,
    WorkflowDef,
    WorkflowVersion,
)
from mailbus.core.workflow.values import AdvanceOutcome


@dataclass(frozen=True, slots=True)
class WorkflowCommand:
    name: str


@dataclass(frozen=True, slots=True)
class VersionCommand:
    """节点名称按执行顺序排列；节点 id 由服务端生成。"""

    nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskCommand:
    title: str
    owner_id: str | None = None
    workflow_id: str | None = None
    workflow_version: int | None = None


@dataclass(frozen=True, slots=True)
class AdvanceCommand:
    node_id: str | None = None
    outcome: AdvanceOutcome = AdvanceOutcome.RUNNING
    note: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowView:
    workflow_id: str
    name: str
    latest_version: int
    published_version: int | None
    created_at: datetime | None

    @classmethod
    def of(cls, definition: WorkflowDef) -> "WorkflowView":
        return cls(
            workflow_id=definition.workflow_id,
            name=definition.name,
            latest_version=definition.latest_version,
            published_version=definition.published_version,
            created_at=definition.created_at,
        )


@dataclass(frozen=True, slots=True)
class VersionNodeView:
    node_id: str
    name: str
    order: int


@dataclass(frozen=True, slots=True)
class VersionView:
    workflow_id: str
    version: int
    state: str
    nodes: tuple[VersionNodeView, ...]
    created_at: datetime | None
    published_at: datetime | None

    @classmethod
    def of(cls, version: WorkflowVersion) -> "VersionView":
        return cls(
            workflow_id=version.workflow_id,
            version=version.version,
            state=version.state.value,
            nodes=tuple(
                VersionNodeView(node_id=node.node_id, name=node.name, order=node.order)
                for node in version.nodes
            ),
            created_at=version.created_at,
            published_at=version.published_at,
        )


@dataclass(frozen=True, slots=True)
class TaskNodeView:
    node_id: str
    name: str
    order: int
    state: str


@dataclass(frozen=True, slots=True)
class TaskView:
    task_id: str
    title: str
    state: str
    workflow_id: str | None
    workflow_version: int | None
    owner_id: str | None
    created_by: str | None
    created_at: datetime | None
    updated_at: datetime | None
    nodes: tuple[TaskNodeView, ...]

    @classmethod
    def of(cls, task: Task, nodes: Sequence[TaskNode] = ()) -> "TaskView":
        return cls(
            task_id=task.task_id,
            title=task.title,
            state=task.state.value,
            workflow_id=task.workflow_id,
            workflow_version=task.workflow_version,
            owner_id=task.owner_id,
            created_by=task.created_by,
            created_at=task.created_at,
            updated_at=task.updated_at,
            nodes=tuple(
                TaskNodeView(
                    node_id=node.node_id,
                    name=node.name,
                    order=node.order,
                    state=node.state.value,
                )
                for node in nodes
            ),
        )


def make_workflow_command(name: str) -> WorkflowCommand:
    return WorkflowCommand(name=name)


def make_version_command(names: Sequence[str]) -> VersionCommand:
    return VersionCommand(nodes=tuple(names))


def make_task_command(
    title: str,
    owner_id: str | None = None,
    workflow_id: str | None = None,
    workflow_version: int | None = None,
) -> TaskCommand:
    return TaskCommand(
        title=title,
        owner_id=owner_id,
        workflow_id=workflow_id,
        workflow_version=workflow_version,
    )


def make_advance_command(
    node_id: str | None, outcome: str, note: str | None = None
) -> AdvanceCommand:
    try:
        parsed = AdvanceOutcome(outcome)
    except ValueError as exc:
        raise InvalidStateError(f"未知推进动作：{outcome}") from exc
    return AdvanceCommand(node_id=node_id, outcome=parsed, note=note)
