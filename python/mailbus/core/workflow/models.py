"""流程上下文的聚合。

- WorkflowDef：定义，记录已分配的最高版本与当前发布版本；
- WorkflowVersion：发布后不可变，任务锁定版本号；
- Task：自由任务与流程任务是同一个聚合，仅 workflow 字段为空与非空的区别。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mailbus.core.workflow.values import (
    NodeState,
    RunState,
    TaskState,
    VersionState,
)

# 六类节点：与设计文档 v4.1 第 192 行一致，begin 节点承担触发入口。
NODE_TYPES = (
    "start",
    "agent",
    "human",
    "condition",
    "parallel_join",
    "final_approval",
)


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """版本内的节点定义；顺序（seq）只用于展示，执行关系由边决定。"""

    node_id: str
    name: str
    order: int
    node_type: str = "agent"
    position_id: str | None = None
    prompt_template: str | None = None
    needs_artifacts_from: tuple[str, ...] = ()
    max_retries: int = 3
    max_loops: int = 3
    timeout_seconds: int | None = None
    config: dict[str, Any] = field(default_factory=dict)
    pos_x: float = 0.0
    pos_y: float = 0.0


@dataclass(frozen=True, slots=True)
class WorkflowEdge:
    """版本内的一条有向边；condition 为空即无条件边。"""

    from_node_id: str
    to_node_id: str
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowVersion:
    workflow_id: str
    version: int
    state: VersionState
    nodes: tuple[WorkflowNode, ...] = ()
    revision: int = 1
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
    deleted_at: datetime | None = None

    @property
    def deleted(self) -> bool:
        return self.deleted_at is not None


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
    termination_reason: str | None = None
    loop_counters: dict[str, int] = field(default_factory=dict)
    archived_at: datetime | None = None

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
    current_run_id: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TaskRun:
    """节点的一次执行实例；扇出分片与重试各自独立 attempt。"""

    run_id: str
    task_id: str
    node_id: str
    attempt_no: int
    state: RunState
    fanout_slot: int = 0
    assigned_employee_id: str | None = None
    role_id: str | None = None
    fanout_group: str | None = None
    short_fanout: bool = False
    result: str | None = None
    parent_run_id: str | None = None
    dispatched_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    deadline_at: datetime | None = None
    escalated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TaskArtifact:
    artifact_id: str
    task_id: str
    node_id: str
    run_id: str
    file_path: str
    file_name: str
    created_by: str
    created_at: datetime | None = None
    artifact_type: str | None = None
    description: str | None = None
    version: int = 1


@dataclass(frozen=True, slots=True)
class TaskEscalation:
    escalation_id: str
    task_id: str
    reason: str
    escalated_to: str
    escalated_at: datetime | None = None
    run_id: str | None = None
    approval_id: str | None = None
    level: int = 1
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution: str | None = None


@dataclass(frozen=True, slots=True)
class TaskVariable:
    task_id: str
    key: str
    value: str
    source: str
    updated_at: datetime | None = None
    updated_by: str | None = None

