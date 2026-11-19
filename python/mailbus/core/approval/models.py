"""审批项聚合。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.approval.values import ApprovalStatus, ApprovalTier


@dataclass(frozen=True, slots=True)
class ApprovalItem:
    approval_id: str
    task_id: str
    title: str
    tier: ApprovalTier
    status: ApprovalStatus
    requester_id: str | None = None
    node_id: str | None = None
    note: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None

    @property
    def pending(self) -> bool:
        return self.status is ApprovalStatus.PENDING
