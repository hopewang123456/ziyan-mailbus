"""approval 协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.approval import ApprovalIn, ApprovalOut, ResolveIn
from mailbus.application.approval.dto import (
    ApprovalCommand,
    ApprovalView,
    ResolveCommand,
    make_approval_command,
    make_resolve_command,
)


def to_approval_out(view: ApprovalView) -> ApprovalOut:
    return ApprovalOut(
        approval_id=view.approval_id,
        task_id=view.task_id,
        node_id=view.node_id,
        title=view.title,
        tier=view.tier,
        status=view.status,
        requester_id=view.requester_id,
        note=view.note,
        created_at=view.created_at,
        expires_at=view.expires_at,
        resolved_by=view.resolved_by,
        resolved_at=view.resolved_at,
        resolution_note=view.resolution_note,
    )


def approval_command(payload: ApprovalIn) -> ApprovalCommand:
    return make_approval_command(
        task_id=payload.task_id,
        title=payload.title,
        tier=payload.tier,
        node_id=payload.node_id,
        note=payload.note,
        timeout_minutes=payload.timeout_minutes,
    )


def resolve_command(payload: ResolveIn) -> ResolveCommand:
    return make_resolve_command(payload.approved, payload.note)
