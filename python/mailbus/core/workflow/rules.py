"""流程与任务的纯函数状态转移。

每个函数返回 (新状态, 领域事件)，不落库、不生成 id、不读时钟。
非法转移抛领域异常；application 负责事务、仓储与事件投递。

版本发布只改版本行与定义指针，任务持有 workflow_version，
因此后续发布会自然不影响运行中的任务。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mailbus.core.shared.errors import (
    InvalidStateError,
    InvalidTransitionError,
    NotFoundError,
)
from mailbus.core.shared.events import DomainEvent
from mailbus.core.workflow.models import (
    Task,
    TaskNode,
    WorkflowDef,
    WorkflowNode,
    WorkflowVersion,
)
from mailbus.core.workflow.values import (
    AdvanceOutcome,
    NodeState,
    TaskState,
    TERMINAL_NODE_STATES,
    TERMINAL_TASK_STATES,
    VersionState,
)

FREE_TARGETS: dict[AdvanceOutcome, TaskState] = {
    AdvanceOutcome.RUNNING: TaskState.RUNNING,
    AdvanceOutcome.DONE: TaskState.DONE,
    AdvanceOutcome.FAILED: TaskState.FAILED,
    AdvanceOutcome.BLOCKED: TaskState.BLOCKED,
    AdvanceOutcome.SKIPPED: TaskState.CANCELLED,
}

FREE_ALLOWED: dict[AdvanceOutcome, frozenset[TaskState]] = {
    AdvanceOutcome.RUNNING: frozenset(
        {TaskState.DRAFT, TaskState.QUEUED, TaskState.RUNNING, TaskState.BLOCKED}
    ),
    AdvanceOutcome.DONE: frozenset({TaskState.QUEUED, TaskState.RUNNING}),
    AdvanceOutcome.FAILED: frozenset({TaskState.DRAFT, TaskState.QUEUED, TaskState.RUNNING}),
    AdvanceOutcome.BLOCKED: frozenset({TaskState.QUEUED, TaskState.RUNNING}),
    AdvanceOutcome.SKIPPED: frozenset(
        {TaskState.DRAFT, TaskState.QUEUED, TaskState.RUNNING, TaskState.BLOCKED}
    ),
}

NODE_TARGETS: dict[AdvanceOutcome, NodeState] = {
    AdvanceOutcome.RUNNING: NodeState.RUNNING,
    AdvanceOutcome.DONE: NodeState.DONE,
    AdvanceOutcome.FAILED: NodeState.FAILED,
    AdvanceOutcome.BLOCKED: NodeState.BLOCKED,
    AdvanceOutcome.SKIPPED: NodeState.SKIPPED,
}

NODE_ALLOWED: dict[AdvanceOutcome, frozenset[NodeState]] = {
    AdvanceOutcome.RUNNING: frozenset(
        {NodeState.DISPATCHED, NodeState.RUNNING, NodeState.BLOCKED}
    ),
    AdvanceOutcome.DONE: frozenset({NodeState.DISPATCHED, NodeState.RUNNING}),
    AdvanceOutcome.FAILED: frozenset({NodeState.DISPATCHED, NodeState.RUNNING}),
    AdvanceOutcome.BLOCKED: frozenset({NodeState.DISPATCHED, NodeState.RUNNING}),
    AdvanceOutcome.SKIPPED: frozenset(
        {NodeState.PENDING, NodeState.DISPATCHED, NodeState.RUNNING, NodeState.BLOCKED}
    ),
}

_ACTIVE_NODE_STATES = frozenset(
    {NodeState.PENDING, NodeState.DISPATCHED, NodeState.RUNNING, NodeState.BLOCKED}
)


def validate_name(value: str, label: str) -> str:
    name = value.strip()
    if not name:
        raise InvalidStateError(f"{label}不能为空")
    if len(name) > 64:
        raise InvalidStateError(f"{label}不能超过 64 个字符")
    return name


def create_definition(
    workflow_id: str, name: str, now: datetime
) -> tuple[WorkflowDef, tuple[DomainEvent, ...]]:
    definition = WorkflowDef(
        workflow_id=workflow_id,
        name=validate_name(name, "流程名称"),
        created_at=now,
    )
    return definition, (
        _event("workflow.created", {"workflow_id": workflow_id, "at": now.isoformat()}),
    )


def rename_definition(
    definition: WorkflowDef, name: str, now: datetime
) -> tuple[WorkflowDef, tuple[DomainEvent, ...]]:
    """重命名定义；版本不可变，只改展示名。"""
    updated_name = validate_name(name, "流程名称")
    if updated_name == definition.name:
        return definition, ()
    updated = replace(definition, name=updated_name)
    return updated, (
        _event(
            "workflow.renamed",
            {"workflow_id": definition.workflow_id, "name": updated_name, "at": now.isoformat()},
        ),
    )


def delete_definition(
    definition: WorkflowDef, now: datetime
) -> tuple[DomainEvent, ...]:
    return (
        _event(
            "workflow.deleted",
            {"workflow_id": definition.workflow_id, "at": now.isoformat()},
        ),
    )


def add_version(
    definition: WorkflowDef, nodes: tuple[WorkflowNode, ...], now: datetime
) -> tuple[WorkflowDef, WorkflowVersion, tuple[DomainEvent, ...]]:
    """新增草稿版本；节点顺序即执行顺序。"""
    if not nodes:
        raise InvalidStateError("流程版本至少需要一个节点")
    names = [node.node_id for node in nodes]
    if len(set(names)) != len(names):
        raise InvalidStateError("节点 id 重复")
    for node in nodes:
        validate_name(node.name, "节点名称")
    version = WorkflowVersion(
        workflow_id=definition.workflow_id,
        version=definition.latest_version + 1,
        state=VersionState.DRAFT,
        nodes=tuple(sorted(nodes, key=lambda item: item.order)),
        created_at=now,
    )
    updated = replace(definition, latest_version=version.version)
    event = _event(
        "workflow.version_created",
        {
            "workflow_id": definition.workflow_id,
            "version": version.version,
            "at": now.isoformat(),
        },
    )
    return updated, version, (event,)


def publish_version(
    definition: WorkflowDef, version: WorkflowVersion, now: datetime
) -> tuple[WorkflowDef, WorkflowVersion, tuple[DomainEvent, ...]]:
    """发布版本：只改版本状态与定义指针，已发布版本不可再改。"""
    if version.published:
        return definition, version, ()
    published = replace(version, state=VersionState.PUBLISHED, published_at=now)
    pointer = max(definition.published_version or 0, version.version)
    updated = replace(definition, published_version=pointer)
    event = _event(
        "workflow.version_published",
        {
            "workflow_id": version.workflow_id,
            "version": version.version,
            "at": now.isoformat(),
        },
    )
    return updated, published, (event,)


def create_task(
    task_id: str,
    title: str,
    *,
    owner_id: str | None,
    created_by: str | None,
    version: WorkflowVersion | None,
    now: datetime,
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    """自由任务与流程任务同一聚合；version 为空即自由任务。"""
    task = Task(
        task_id=task_id,
        title=validate_name(title, "任务标题"),
        state=TaskState.DRAFT,
        workflow_id=version.workflow_id if version else None,
        workflow_version=version.version if version else None,
        owner_id=owner_id,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    nodes = (
        tuple(
            TaskNode(
                task_id=task_id,
                node_id=node.node_id,
                name=node.name,
                order=node.order,
                state=NodeState.PENDING,
                updated_at=now,
            )
            for node in version.nodes
        )
        if version
        else ()
    )
    event = _event(
        "task.created",
        {
            "task_id": task_id,
            "workflow_id": task.workflow_id,
            "workflow_version": task.workflow_version,
            "owner_id": owner_id,
            "at": now.isoformat(),
        },
    )
    return task, nodes, (event,)


def dispatch(
    task: Task, nodes: tuple[TaskNode, ...], now: datetime
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    """派发：任务进入队列，首个待执行节点进入 dispatched。"""
    if task.state not in (TaskState.DRAFT, TaskState.QUEUED):
        raise InvalidTransitionError("只有草稿或排队中的任务可以派发")
    queued = replace(task, state=TaskState.QUEUED, updated_at=now)
    updated = (
        _dispatch_next(nodes, now)
        if task.workflow_version is not None
        else nodes
    )
    current = next((node for node in updated if node.state is NodeState.DISPATCHED), None)
    return queued, tuple(updated), (
        _event(
            "task.dispatched",
            {
                "task_id": task.task_id,
                "owner_id": task.owner_id,
                "node_id": current.node_id if current else None,
                "at": now.isoformat(),
            },
        ),
    )


def advance(
    task: Task,
    nodes: tuple[TaskNode, ...],
    *,
    node_id: str | None,
    outcome: AdvanceOutcome,
    now: datetime,
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    """推进任务：自由任务直接改任务状态，流程任务按节点推进。"""
    if task.state in TERMINAL_TASK_STATES:
        raise InvalidTransitionError("任务已结束，不能继续推进")
    if task.workflow_version is None:
        return _advance_free(task, outcome, now)
    return _advance_workflow(task, nodes, node_id=node_id, outcome=outcome, now=now)


def cancel(
    task: Task, nodes: tuple[TaskNode, ...], now: datetime
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    """取消：幂等；未结束的节点统一置为 skipped。"""
    if task.state in TERMINAL_TASK_STATES:
        return task, nodes, ()
    cancelled = replace(task, state=TaskState.CANCELLED, updated_at=now)
    skipped = tuple(
        node
        if node.state in TERMINAL_NODE_STATES
        else replace(node, state=NodeState.SKIPPED, updated_at=now)
        for node in nodes
    )
    return cancelled, skipped, (
        _event("task.cancelled", {"task_id": task.task_id, "at": now.isoformat()}),
    )


def _advance_free(
    task: Task, outcome: AdvanceOutcome, now: datetime
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    if task.state not in FREE_ALLOWED[outcome]:
        raise InvalidTransitionError(
            f"任务状态 {task.state.value} 不能执行 {outcome.value}"
        )
    updated = replace(task, state=FREE_TARGETS[outcome], updated_at=now)
    return updated, (), (_event(_event_kind(updated.state, outcome), _payload(updated, now)),)


def _advance_workflow(
    task: Task,
    nodes: tuple[TaskNode, ...],
    *,
    node_id: str | None,
    outcome: AdvanceOutcome,
    now: datetime,
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    index = _node_index(nodes, node_id)
    current = nodes[index]
    if current.state not in NODE_ALLOWED[outcome]:
        raise InvalidTransitionError(
            f"节点状态 {current.state.value} 不能执行 {outcome.value}"
        )
    updated = list(nodes)
    updated[index] = replace(current, state=NODE_TARGETS[outcome], updated_at=now)
    if outcome in (AdvanceOutcome.DONE, AdvanceOutcome.SKIPPED):
        updated = _dispatch_next(updated, now)
    state = _task_state_after(updated, outcome)
    changed = replace(task, state=state, updated_at=now)
    payload = _payload(changed, now)
    payload["node_id"] = current.node_id
    return changed, tuple(updated), (_event(_event_kind(state, outcome), payload),)


def _node_index(nodes: tuple[TaskNode, ...], node_id: str | None) -> int:
    if node_id is not None:
        for index, node in enumerate(nodes):
            if node.node_id == node_id:
                return index
        raise NotFoundError("任务节点不存在")
    for index, node in enumerate(nodes):
        if node.state in (
            NodeState.DISPATCHED,
            NodeState.RUNNING,
            NodeState.BLOCKED,
        ):
            return index
    for index, node in enumerate(nodes):
        if node.state is NodeState.PENDING:
            return index
    raise InvalidStateError("任务没有可推进的节点")


def _task_state_after(nodes: list[TaskNode], outcome: AdvanceOutcome) -> TaskState:
    if outcome is AdvanceOutcome.FAILED:
        return TaskState.FAILED
    if outcome is AdvanceOutcome.BLOCKED:
        return TaskState.BLOCKED
    if outcome is AdvanceOutcome.RUNNING:
        return TaskState.RUNNING
    if any(node.state in _ACTIVE_NODE_STATES for node in nodes):
        return TaskState.RUNNING
    if any(node.state is NodeState.FAILED for node in nodes):
        return TaskState.FAILED
    return TaskState.DONE


def _dispatch_next(nodes: tuple[TaskNode, ...] | list[TaskNode], now: datetime):
    """把下一个 pending 节点置为 dispatched；已有活跃节点时保持不动。"""
    items = list(nodes)
    if any(
        node.state in (NodeState.DISPATCHED, NodeState.RUNNING, NodeState.BLOCKED)
        for node in items
    ):
        return items
    for index, node in enumerate(items):
        if node.state is NodeState.PENDING:
            items[index] = replace(node, state=NodeState.DISPATCHED, updated_at=now)
            break
    return items


def _payload(task: Task, now: datetime) -> dict[str, object]:
    return {"task_id": task.task_id, "state": task.state.value, "at": now.isoformat()}


def _event_kind(state: TaskState, outcome: AdvanceOutcome) -> str:
    if state is TaskState.DONE:
        return "task.completed"
    if state is TaskState.FAILED:
        return "task.failed"
    if state is TaskState.BLOCKED:
        return "task.blocked"
    if outcome is AdvanceOutcome.RUNNING:
        return "task.started"
    if outcome is AdvanceOutcome.SKIPPED:
        return "task.node_skipped"
    return "task.advanced"


def _event(kind: str, payload: dict[str, object]) -> DomainEvent:
    return DomainEvent(kind=kind, payload=dict(payload))
