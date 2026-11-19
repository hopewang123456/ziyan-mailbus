"""task 分组的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    owner_id: str | None = None
    workflow_id: str | None = None
    workflow_version: int | None = None


class TaskAdvanceIn(BaseModel):
    node_id: str | None = None
    outcome: Literal["running", "done", "failed", "blocked", "skipped"] = "running"
    note: str | None = None


class TaskNodeOut(BaseModel):
    node_id: str
    name: str
    order: int
    state: str


class TaskOut(BaseModel):
    task_id: str
    title: str
    state: str
    workflow_id: str | None = None
    workflow_version: int | None = None
    owner_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    nodes: list[TaskNodeOut]
