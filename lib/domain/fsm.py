"""Task / Step FSM state enums (domain)."""
from __future__ import annotations

from enum import Enum


class TaskFsmState(str, Enum):
    CREATED = "created"
    EXECUTING = "executing"
    ACCEPTING = "accepting"  # 链完成，等待人工终验
    BLOCKED = "blocked"  # 步骤 fail 等待人工决策
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepFsmState(str, Enum):
    PENDING = "pending"  # 尚未轮到
    QUEUED = "queued"  # 等待 dispatch
    DISPATCHED = "dispatched"  # 消息已写入 inbox
    IN_PROGRESS = "in_progress"  # agent 已 ack / CLI 活跃
    AWAITING_RESULT = "awaiting_result"  # 等待 msg-results
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    SUPERSEDED = "superseded"  # 被回退覆盖


__all__ = ["StepFsmState", "TaskFsmState"]
