"""强类型标识符。

跨上下文只允许传 id，不允许传实体：上下文之间靠 id 与用例调用协作。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Identifier:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError(f"{type(self).__name__} 不能为空")

    def __str__(self) -> str:
        return self.value


class AgentId(_Identifier):
    """员工标识（真人与 Agent 同表，role 由 Employee 区分）。"""


class TeamId(_Identifier):
    """团队标识。"""


class PositionId(_Identifier):
    """岗位标识（权限模板）。"""


class SeatId(_Identifier):
    """工位标识。"""


class WorkflowId(_Identifier):
    """工作流定义标识。"""


class TaskId(_Identifier):
    """任务标识。"""


class NodeId(_Identifier):
    """工作流节点标识。"""


class MessageId(_Identifier):
    """消息标识。"""


class ApprovalId(_Identifier):
    """审批项标识。"""
