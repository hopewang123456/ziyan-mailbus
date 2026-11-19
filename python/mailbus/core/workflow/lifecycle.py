"""任务的阻塞与结束转移（审批等外部裁决使用）。

与 rules 同为纯函数：返回新状态与领域事件，不落库、不读时钟。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mailbus.core.shared.errors import InvalidTransitionError
from mailbus.core.shared.events import DomainEvent
from mailbus.core.workflow.models import Task, TaskNode
from mailbus.core.workflow.values import (
    NodeState,
    TaskState,
    TERMINAL_NODE_STATES,
    TERMINAL_TASK_STATES,
)


def hold(
    task: Task, nodes: tuple[TaskNode, ...], *, reason: str, now: datetime
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    """阻塞任务（如等待阻塞档审批）；活跃节点一并置为 blocked。"""
    if task.state in TERMINAL_TASK_STATES:
        raise InvalidTransitionError("任务已结束，不能阻塞")
    blocked = replace(task, state=TaskState.BLOCKED, updated_at=now)
    held = tuple(
        replace(node, state=NodeState.BLOCKED, updated_at=now)
        if node.state in (NodeState.DISPATCHED, NodeState.RUNNING)
        else node
        for node in nodes
    )
    payload = {**_payload(blocked, now), "reason": reason}
    return blocked, held, (_event("task.blocked", payload),)


def resume(
    task: Task, nodes: tuple[TaskNode, ...], now: datetime
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    """解除阻塞：任务回到 running，阻塞中的节点恢复执行。"""
    if task.state is not TaskState.BLOCKED:
        raise InvalidTransitionError("只有阻塞中的任务可以恢复")
    running = replace(task, state=TaskState.RUNNING, updated_at=now)
    resumed = tuple(
        replace(node, state=NodeState.RUNNING, updated_at=now)
        if node.state is NodeState.BLOCKED
        else node
        for node in nodes
    )
    return running, resumed, (_event("task.resumed", _payload(running, now)),)


def fail(
    task: Task, nodes: tuple[TaskNode, ...], *, reason: str, now: datetime
) -> tuple[Task, tuple[TaskNode, ...], tuple[DomainEvent, ...]]:
    """任务失败：已失败幂等，其余未结束状态统一置为 failed。"""
    if task.state is TaskState.FAILED:
        return task, nodes, ()
    if task.state in TERMINAL_TASK_STATES:
        raise InvalidTransitionError("任务已结束，不能标记失败")
    failed = replace(task, state=TaskState.FAILED, updated_at=now)
    marked = tuple(
        node
        if node.state in TERMINAL_NODE_STATES
        else replace(node, state=NodeState.FAILED, updated_at=now)
        for node in nodes
    )
    payload = {**_payload(failed, now), "reason": reason}
    return failed, marked, (_event("task.failed", payload),)


def _payload(task: Task, now: datetime) -> dict[str, object]:
    return {"task_id": task.task_id, "state": task.state.value, "at": now.isoformat()}


def _event(kind: str, payload: dict[str, object]) -> DomainEvent:
    return DomainEvent(kind=kind, payload=dict(payload))
