"""流程上下文的聚合。

- WorkflowDef：定义，记录已分配的最高版本与当前发布版本；
- WorkflowVersion：发布后不可变，任务锁定版本号；
- Task：自由任务与流程任务是同一个聚合，仅 workflow 字段为空与非空的区别。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.workflow.values import NodeState, TaskState, VersionState


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """版本内的节点定义；顺序即执行顺序。"""

    node_id: str
    name: str
    order: int


@dataclass(frozen=True, slots=True)
class WorkflowVersion:
    workflow_id: str
    version: int
    state: VersionState
    nodes: tuple[WorkflowNode, ...] = ()
    created_at: datetime | None = None
    published_at: datetime | None = None

    @property
    def published(self) -> bool:
        return self.state is VersionState.PUBLISHED


@dataclass(frozen=True, slots=True)
class WorkflowDef:
    workflow_id: str
    name: str
    latest_version: int = 0
    published_version: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    title: str
    state: TaskState
    workflow_id: str | None = None
    workflow_version: int | None = None
    owner_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_free(self) -> bool:
        return self.workflow_version is None


@dataclass(frozen=True, slots=True)
class TaskNode:
    """任务节点实例：状态属于任务，不属于版本定义。"""

    task_id: str
    node_id: str
    name: str
    order: int
    state: NodeState = NodeState.PENDING
    updated_at: datetime | None = None
