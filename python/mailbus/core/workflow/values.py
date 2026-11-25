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
    """任务聚合态；draft/queued 仅为旧行兼容，新任务不再产生。"""

    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DRAFT = "draft"
    QUEUED = "queued"


class RunState(str, Enum):
    """节点执行实例状态；waiting_human 表示共享人工待办。"""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class TerminationReason(str, Enum):
    """任务终止原因（task_tasks.termination_reason）。"""

    MANUAL = "manual"
    NO_MATCHING_BRANCH = "no_matching_branch"
    AUTO_TERMINATED = "auto_terminated"
    APPROVAL_REJECTED = "approval_rejected"


class EscalationReason(str, Enum):
    APPROVAL_TIMEOUT = "approval_timeout"
    WORK_TIMEOUT = "work_timeout"
    LOOP_EXCEEDED = "loop_exceeded"
    RUN_FAILED = "run_failed"


class NodeState(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


TASK_STATE_TAGS: dict[TaskState, SemanticTag] = {
    TaskState.PENDING: SemanticTag.START,
    TaskState.DRAFT: SemanticTag.START,
    TaskState.QUEUED: SemanticTag.START,
    TaskState.RUNNING: SemanticTag.ACTIVE,
    TaskState.BLOCKED: SemanticTag.BLOCKED,
    TaskState.DONE: SemanticTag.SUCCESS,
    TaskState.FAILED: SemanticTag.FAILURE,
    TaskState.CANCELLED: SemanticTag.CANCELLED,
}

RUN_STATE_TAGS: dict[RunState, SemanticTag] = {
    RunState.PENDING: SemanticTag.START,
    RunState.DISPATCHED: SemanticTag.ACTIVE,
    RunState.RUNNING: SemanticTag.ACTIVE,
    RunState.WAITING_HUMAN: SemanticTag.BLOCKED,
    RunState.DONE: SemanticTag.SUCCESS,
    RunState.FAILED: SemanticTag.FAILURE,
    RunState.SKIPPED: SemanticTag.CANCELLED,
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

# 「手上有业务」：已派发、执行中、阻塞都算忙，布局与概览共用同一口径。
BUSY_TASK_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.PENDING,
        TaskState.QUEUED,
        TaskState.RUNNING,
        TaskState.BLOCKED,
    }
)

TERMINAL_NODE_STATES: frozenset[NodeState] = frozenset(
    {NodeState.DONE, NodeState.FAILED, NodeState.SKIPPED}
)

TERMINAL_RUN_STATES: frozenset[RunState] = frozenset(
    {RunState.DONE, RunState.FAILED, RunState.SKIPPED}
)

OPEN_RUN_STATES: frozenset[RunState] = frozenset(
    {
        RunState.PENDING,
        RunState.DISPATCHED,
        RunState.RUNNING,
        RunState.WAITING_HUMAN,
    }
)

# 节点类型中无需人工/AI 执行的自动节点。
AUTOMATIC_NODE_TYPES: frozenset[str] = frozenset({"start", "condition"})

DEFAULT_WORK_TIMEOUT_SECONDS = 72 * 3600
DEFAULT_APPROVAL_TIMEOUT_MINUTES = 24 * 60
DEFAULT_FANOUT_WAIT_SECONDS = 600

# 一级升级后仍无人处理，72 小时自动终止任务（设计 10.17）。
ESCALATION_TERMINATE_SECONDS = 72 * 3600

