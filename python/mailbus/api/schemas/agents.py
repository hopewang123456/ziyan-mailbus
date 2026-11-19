"""Agent 台账的对外模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    framework: str = Field(default="", max_length=64)
    model: str | None = None
    endpoint: str | None = None
    enabled: bool = True


class AgentUpdateIn(BaseModel):
    """PATCH 语义：只提交需要修改的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    framework: str | None = Field(default=None, max_length=64)
    model: str | None = None
    endpoint: str | None = None
    enabled: bool | None = None


class AgentOut(BaseModel):
    agent_id: str
    name: str
    framework: str
    model: str | None = None
    endpoint: str | None = None
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
