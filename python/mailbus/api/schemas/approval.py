"""approval 分组的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApprovalIn(BaseModel):
    task_id: str
    title: str = Field(min_length=1, max_length=64)
    tier: Literal["blocking", "advisory", "informational"]
    node_id: str | None = None
    note: str | None = None
    timeout_minutes: int | None = Field(default=None, gt=0)


class ResolveIn(BaseModel):
    approved: bool
    note: str | None = None


class ApprovalOut(BaseModel):
    approval_id: str
    task_id: str
    node_id: str | None = None
    title: str
    tier: str
    status: str
    requester_id: str | None = None
    note: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
