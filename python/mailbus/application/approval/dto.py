"""审批用例的输入/输出模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.approval.models import ApprovalItem
from mailbus.core.approval.values import ApprovalTier
from mailbus.core.shared.errors import InvalidStateError


@dataclass(frozen=True, slots=True)
class ApprovalCommand:
    task_id: str
    title: str
    tier: ApprovalTier
    node_id: str | None = None
    note: str | None = None
    timeout_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class ResolveCommand:
    approved: bool
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovalView:
    approval_id: str
    task_id: str
    node_id: str | None
    title: str
    tier: str
    status: str
    requester_id: str | None
    note: str | None
    created_at: datetime | None
    expires_at: datetime | None
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_note: str | None

    @classmethod
    def of(cls, item: ApprovalItem) -> "ApprovalView":
        return cls(
            approval_id=item.approval_id,
            task_id=item.task_id,
            node_id=item.node_id,
            title=item.title,
            tier=item.tier.value,
            status=item.status.value,
            requester_id=item.requester_id,
            note=item.note,
            created_at=item.created_at,
            expires_at=item.expires_at,
            resolved_by=item.resolved_by,
            resolved_at=item.resolved_at,
            resolution_note=item.resolution_note,
        )


def make_approval_command(
    task_id: str,
    title: str,
    tier: str,
    node_id: str | None = None,
    note: str | None = None,
    timeout_minutes: int | None = None,
) -> ApprovalCommand:
    try:
        parsed = ApprovalTier(tier)
    except ValueError as exc:
        raise InvalidStateError(f"未知审批档位：{tier}") from exc
    return ApprovalCommand(
        task_id=task_id,
        title=title,
        tier=parsed,
        node_id=node_id,
        note=note,
        timeout_minutes=timeout_minutes,
    )


def make_resolve_command(approved: bool, note: str | None = None) -> ResolveCommand:
    return ResolveCommand(approved=approved, note=note)
