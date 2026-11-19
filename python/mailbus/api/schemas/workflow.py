"""workflow 分组的对外模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class WorkflowOut(BaseModel):
    workflow_id: str
    name: str
    latest_version: int
    published_version: int | None = None
    created_at: datetime | None = None


class VersionNodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class VersionIn(BaseModel):
    nodes: list[VersionNodeIn] = Field(min_length=1)


class VersionNodeOut(BaseModel):
    node_id: str
    name: str
    order: int


class VersionOut(BaseModel):
    workflow_id: str
    version: int
    state: str
    nodes: list[VersionNodeOut]
    created_at: datetime | None = None
    published_at: datetime | None = None
