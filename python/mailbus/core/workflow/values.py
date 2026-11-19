"""任务与节点状态的唯一枚举源。

规则：
- 状态定义只允许出现在 core（守卫 G7）；
- 每个状态必须能映射到语义标签，否则自定义状态拒绝保存。
"""

from __future__ import annotations

from enum import Enum

from mailbus.core.shared.values import SemanticTag


class VersionState(str, Enum):
    """流程版本状态：草稿可改，发布后不可变。"""

    DRAFT = "draft"
    PUBLISHED = "published"


class AdvanceOutcome(str, Enum):
    """任务推进的输入动作；对自由任务和流程节点通用。"""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TaskState(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeState(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


TASK_STATE_TAGS: dict[TaskState, SemanticTag] = {
    TaskState.DRAFT: SemanticTag.START,
    TaskState.QUEUED: SemanticTag.START,
    TaskState.RUNNING: SemanticTag.ACTIVE,
    TaskState.BLOCKED: SemanticTag.BLOCKED,
    TaskState.DONE: SemanticTag.SUCCESS,
    TaskState.FAILED: SemanticTag.FAILURE,
    TaskState.CANCELLED: SemanticTag.CANCELLED,
}

NODE_STATE_TAGS: dict[NodeState, SemanticTag] = {
    NodeState.PENDING: SemanticTag.START,
    NodeState.DISPATCHED: SemanticTag.ACTIVE,
    NodeState.RUNNING: SemanticTag.ACTIVE,
    NodeState.BLOCKED: SemanticTag.BLOCKED,
    NodeState.DONE: SemanticTag.SUCCESS,
    NodeState.FAILED: SemanticTag.FAILURE,
    NodeState.SKIPPED: SemanticTag.CANCELLED,
}


def semantic_tag_of(state: TaskState) -> SemanticTag:
    return TASK_STATE_TAGS[state]


def is_terminal(state: TaskState) -> bool:
    return TASK_STATE_TAGS[state] in (SemanticTag.SUCCESS, SemanticTag.FAILURE, SemanticTag.CANCELLED)


TERMINAL_TASK_STATES: frozenset[TaskState] = frozenset(
    {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}
)

TERMINAL_NODE_STATES: frozenset[NodeState] = frozenset(
    {NodeState.DONE, NodeState.FAILED, NodeState.SKIPPED}
)
