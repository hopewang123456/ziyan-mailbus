"""流程用例的输入/输出模型（application 内部 DTO）。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from mailbus.application.workflow.validation import Issue
from mailbus.core.workflow.models import (
    Task,
    TaskNode,
    WorkflowDef,
    WorkflowEdge,
    WorkflowNode,
    WorkflowVersion,
)


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
    revision: int
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
            revision=version.revision,
            created_at=version.created_at,
            published_at=version.published_at,
        )


@dataclass(frozen=True, slots=True)
class GraphNodeCommand:
    node_id: str
    name: str
    node_type: str
    position_id: str | None
    seq: int
    prompt_template: str | None
    needs_artifacts_from: tuple[str, ...]
    max_retries: int
    max_loops: int
    timeout_seconds: int | None
    config: dict[str, object]
    pos_x: float
    pos_y: float

    def to_model(self) -> WorkflowNode:
        return WorkflowNode(
            node_id=self.node_id,
            name=self.name,
            order=self.seq,
            node_type=self.node_type,
            position_id=self.position_id,
            prompt_template=self.prompt_template,
            needs_artifacts_from=self.needs_artifacts_from,
            max_retries=self.max_retries,
            max_loops=self.max_loops,
            timeout_seconds=self.timeout_seconds,
            config=dict(self.config),
            pos_x=self.pos_x,
            pos_y=self.pos_y,
        )


@dataclass(frozen=True, slots=True)
class GraphEdgeCommand:
    from_node_id: str
    to_node_id: str
    condition: str | None

    def to_model(self) -> WorkflowEdge:
        return WorkflowEdge(
            from_node_id=self.from_node_id,
            to_node_id=self.to_node_id,
            condition=self.condition,
        )


@dataclass(frozen=True, slots=True)
class GraphNodeView:
    node_id: str
    name: str
    node_type: str
    position_id: str | None
    seq: int
    prompt_template: str | None
    needs_artifacts_from: tuple[str, ...]
    max_retries: int
    max_loops: int
    timeout_seconds: int | None
    config: dict[str, object]
    pos_x: float
    pos_y: float


@dataclass(frozen=True, slots=True)
class GraphEdgeView:
    from_node_id: str
    to_node_id: str
    condition: str | None


@dataclass(frozen=True, slots=True)
class GraphView:
    nodes: tuple[GraphNodeView, ...]
    edges: tuple[GraphEdgeView, ...]
    revision: int

    @classmethod
    def of(
        cls,
        nodes: Sequence[WorkflowNode],
        edges: Sequence[WorkflowEdge],
        revision: int,
    ) -> "GraphView":
        return cls(
            nodes=tuple(
                GraphNodeView(
                    node_id=node.node_id,
                    name=node.name,
                    node_type=node.node_type,
                    position_id=node.position_id,
                    seq=node.order,
                    prompt_template=node.prompt_template,
                    needs_artifacts_from=tuple(node.needs_artifacts_from),
                    max_retries=node.max_retries,
                    max_loops=node.max_loops,
                    timeout_seconds=node.timeout_seconds,
                    config=dict(node.config or {}),
                    pos_x=node.pos_x,
                    pos_y=node.pos_y,
                )
                for node in nodes
            ),
            edges=tuple(
                GraphEdgeView(
                    from_node_id=edge.from_node_id,
                    to_node_id=edge.to_node_id,
                    condition=edge.condition,
                )
                for edge in edges
            ),
            revision=revision,
        )


@dataclass(frozen=True, slots=True)
class ValidateIssueView:
    code: str
    message_zh: str
    node_id: str | None
    edge: tuple[str, str] | None

    @classmethod
    def of(cls, issue: Issue) -> "ValidateIssueView":
        return cls(
            code=issue.code,
            message_zh=issue.message_zh,
            node_id=issue.node_id,
            edge=None
            if issue.edge is None
            else (issue.edge.from_node_id, issue.edge.to_node_id),
        )


@dataclass(frozen=True, slots=True)
class ValidateView:
    ok: bool
    errors: tuple[ValidateIssueView, ...]
    warnings: tuple[ValidateIssueView, ...]
    stats: dict[str, object]

    def error_details(self) -> tuple[dict[str, object], ...]:
        return tuple(_issue_detail(item) for item in self.errors)


def _issue_detail(item: ValidateIssueView) -> dict[str, object]:
    detail: dict[str, object] = {"code": item.code, "message_zh": item.message_zh}
    if item.node_id is not None:
        detail["node_id"] = item.node_id
    if item.edge is not None:
        detail["edge"] = {"from_node_id": item.edge[0], "to_node_id": item.edge[1]}
    return detail


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
