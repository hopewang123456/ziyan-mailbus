"""审批的纯函数规则：请求、裁决、超时。

信息档在创建时即确认；阻塞档的任务状态变化由用例层调用 workflow 规则完成，
本模块只负责审批项自身的状态机。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from mailbus.core.approval.models import ApprovalItem
from mailbus.core.approval.values import (
    DEFAULT_TIMEOUT_MINUTES,
    ApprovalStatus,
    ApprovalTier,
)
from mailbus.core.shared.errors import InvalidStateError, InvalidTransitionError
from mailbus.core.shared.events import DomainEvent


def validate_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise InvalidStateError("审批标题不能为空")
    if len(title) > 64:
        raise InvalidStateError("审批标题不能超过 64 个字符")
    return title


def request(
    approval_id: str,
    *,
    task_id: str,
    title: str,
    tier: ApprovalTier,
    requester_id: str | None,
    node_id: str | None,
    note: str | None,
    now: datetime,
    timeout_minutes: int | None = None,
) -> tuple[ApprovalItem, tuple[DomainEvent, ...]]:
    minutes = DEFAULT_TIMEOUT_MINUTES if timeout_minutes is None else timeout_minutes
    if minutes <= 0:
        raise InvalidStateError("审批超时时间必须大于 0")
    acknowledged = tier is ApprovalTier.INFORMATIONAL
    item = ApprovalItem(
        approval_id=approval_id,
        task_id=task_id,
        title=validate_title(title),
        tier=tier,
        status=ApprovalStatus.ACKNOWLEDGED if acknowledged else ApprovalStatus.PENDING,
        requester_id=requester_id,
        node_id=node_id,
        note=note,
        created_at=now,
        expires_at=now + timedelta(minutes=minutes),
        resolved_at=now if acknowledged else None,
    )
    event = DomainEvent(
        kind="approval.requested",
        payload={
            "approval_id": approval_id,
            "task_id": task_id,
            "tier": tier.value,
            "status": item.status.value,
            "at": now.isoformat(),
        },
    )
    return item, (event,)


def resolve(
    item: ApprovalItem,
    *,
    approved: bool,
    resolver_id: str,
    note: str | None,
    now: datetime,
) -> tuple[ApprovalItem, tuple[DomainEvent, ...]]:
    if item.status is ApprovalStatus.ACKNOWLEDGED:
        raise InvalidTransitionError("信息档审批无需裁决")
    if item.status is ApprovalStatus.EXPIRED:
        raise InvalidTransitionError("审批已超时")
    if item.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
        if (item.status is ApprovalStatus.APPROVED) is approved:
            return item, ()
        raise InvalidTransitionError("审批已裁决")
    status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    resolved = replace(
        item,
        status=status,
        resolved_by=resolver_id,
        resolved_at=now,
        resolution_note=note,
    )
    event = DomainEvent(
        kind="approval.approved" if approved else "approval.rejected",
        payload={
            "approval_id": item.approval_id,
            "task_id": item.task_id,
            "resolver_id": resolver_id,
            "at": now.isoformat(),
        },
    )
    return resolved, (event,)


def expire(item: ApprovalItem, now: datetime) -> tuple[ApprovalItem, tuple[DomainEvent, ...]]:
    """只有未裁决且到期的审批会过期；其余原样返回。"""
    if not item.pending or item.expires_at is None or item.expires_at > now:
        return item, ()
    expired = replace(item, status=ApprovalStatus.EXPIRED, resolved_at=now)
    event = DomainEvent(
        kind="approval.expired",
        payload={
            "approval_id": item.approval_id,
            "task_id": item.task_id,
            "tier": item.tier.value,
            "at": now.isoformat(),
        },
    )
    return expired, (event,)


def withdraw(
    item: ApprovalItem, *, actor_id: str, now: datetime
) -> tuple[ApprovalItem, tuple[DomainEvent, ...]]:
    """撤回：仅待裁决的审批可撤回；阻塞档的任务由用例层恢复。"""
    if not item.pending:
        raise InvalidTransitionError("只有待裁决审批可以撤回")
    withdrawn = replace(
        item,
        status=ApprovalStatus.WITHDRAWN,
        resolved_by=actor_id,
        resolved_at=now,
    )
    event = DomainEvent(
        kind="approval.withdrawn",
        payload={
            "approval_id": item.approval_id,
            "task_id": item.task_id,
            "tier": item.tier.value,
            "actor_id": actor_id,
            "at": now.isoformat(),
        },
    )
    return withdrawn, (event,)
