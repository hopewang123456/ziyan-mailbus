"""权限判定的唯一实现（纯函数）。

四层依次判定：账号可用 → 能力 → 数据范围 → 文件范围 → 端点审核。
api 层只负责把 token 解析成 Subject，判定只在 application 用例里调用本模块。
"""

from __future__ import annotations

from dataclasses import dataclass

from mailbus.core.identity.models import Subject
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.errors import PermissionDeniedError
from mailbus.core.shared.values import Capability, DataScope

# 需要 Agent 端点审核通过才能执行的外向动作
_ENDPOINT_GATED: frozenset[Capability] = frozenset(
    {Capability.MESSAGE_SEND, Capability.TASK_DISPATCH, Capability.RESULT_SUBMIT}
)


@dataclass(frozen=True, slots=True)
class Resource:
    """待访问资源；未提供的维度视为不限制。"""

    kind: str
    owner_id: str | None = None
    team_id: str | None = None
    path: str | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str


def decide(subject: Subject, action: Capability, resource: Resource | None = None) -> Decision:
    target = resource or Resource(kind="identity")
    if subject.status is not EmployeeStatus.ACTIVE:
        return Decision(False, "账号未激活或已注销")
    if Capability.ALL not in subject.capabilities and action not in subject.capabilities:
        return Decision(False, f"缺少能力 {action.value}")
    if not _scope_allows(subject, target):
        return Decision(False, "超出数据可见范围")
    if target.path is not None and not subject.file_scope.covers(target.path):
        return Decision(False, "超出工作区文件范围")
    if (
        subject.account_type is AccountType.AGENT
        and action in _ENDPOINT_GATED
        and not subject.endpoint_approved
    ):
        return Decision(False, "Agent 端点尚未通过审核")
    return Decision(True, "allowed")


def ensure_active(subject: Subject) -> None:
    """仅要求账号可用；用于「登录即可、无特定能力」的写用例。"""
    if subject.status is not EmployeeStatus.ACTIVE:
        raise PermissionDeniedError("账号未激活或已注销")


def ensure_allowed(
    subject: Subject, action: Capability, resource: Resource | None = None
) -> None:
    """判定失败即抛 PermissionDeniedError，调用方无需再判断布尔值。"""
    decision = decide(subject, action, resource)
    if not decision.allowed:
        raise PermissionDeniedError(f"权限不足：{decision.reason}")


def ensure_any_allowed(
    subject: Subject,
    actions: tuple[Capability, ...],
    resource: Resource | None = None,
) -> None:
    """任一能力通过即可；全部失败时抛出统一权限错误。"""
    decisions = [decide(subject, action, resource) for action in actions]
    if any(decision.allowed for decision in decisions):
        return
    reason = decisions[0].reason if decisions else "缺少能力"
    raise PermissionDeniedError(f"权限不足：{reason}")


def _scope_allows(subject: Subject, resource: Resource) -> bool:
    if subject.data_scope is DataScope.GLOBAL:
        return True
    if subject.data_scope is DataScope.TEAM:
        if resource.team_id is not None:
            return resource.team_id == subject.team_id
        if resource.owner_id is not None:
            return resource.owner_id == subject.employee_id
        return True
    # SELF：只能触达自己的资源，且不能触达团队级资源
    if resource.team_id is not None:
        return False
    if resource.owner_id is not None:
        return resource.owner_id == subject.employee_id
    return True
