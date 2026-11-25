"""Agent / A2A 域契约模型：外壳、token、审批、邀请与单入口消息。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from mailbus.api.schemas.contract.common import Page

A2aType = Literal["message", "result", "heartbeat", "ack"]
A2aResultStatus = Literal[
    "completed", "failed", "needs_human", "needs_info", "rejected"
]


class AgentOut(BaseModel):
    agent_id: str
    name: str
    framework: str = ""
    model: str | None = None
    endpoint: str | None = None
    pending_endpoint: str | None = None
    endpoint_review_status: str = "pending"
    enabled: bool = True
    agent_type: str = "service"
    channel_type: str = "a2a"
    online: bool = False
    last_seen_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentListOut(Page[AgentOut]):
    pass


class AgentTokenOut(BaseModel):
    agent_id: str
    token: str = Field(description="明文仅签发/轮转响应返回一次")
    fingerprint: str
    expires_at: datetime | None = None


class AgentHealthOut(BaseModel):
    agent_id: str
    online: bool
    endpoint_ok: bool
    last_seen_at: datetime | None = None


class EndpointDecisionIn(BaseModel):
    note: str | None = None


class AgentRegisterIn(BaseModel):
    invite_code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    framework: str = Field(default="", max_length=64)
    model: str | None = None
    endpoint: str | None = None
    agent_type: str = "external"
    channel_type: Literal["a2a", "file_bus", "pull_only"] = "a2a"


class AgentRegisterOut(BaseModel):
    agent_id: str
    employee_id: str | None = None
    token: str = Field(description="明文仅注册响应返回一次")
    endpoint: str | None = None
    endpoint_review_status: str = "pending"


class AgentInviteIn(BaseModel):
    employee_name: str | None = Field(default=None, max_length=64)
    position_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    data_scope: Literal["self", "team", "global"] = "self"
    agent_type: str = "external"
    channel_type: Literal["a2a", "file_bus", "pull_only"] = "a2a"
    expires_in_hours: int | None = Field(
        default=None, ge=1, le=8760, description="null 表示长期有效"
    )


class AgentInviteOut(BaseModel):
    invite_id: str
    invite_code: str | None = Field(default=None, description="明文仅创建响应返回一次")
    employee_name: str | None = None
    position_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    data_scope: str = "self"
    agent_type: str = "external"
    channel_type: str = "a2a"
    created_by: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    used_by_agent_id: str | None = None
    used_at: datetime | None = None
    revoked_at: datetime | None = None


class AgentInviteListOut(Page[AgentInviteOut]):
    pass


class A2aArtifactIn(BaseModel):
    type: Literal["path", "artifact"]
    file_path: str | None = None
    artifact_id: str | None = None
    file_name: str | None = None
    description: str | None = None


class A2aMessageIn(BaseModel):
    type: A2aType = "message"
    message_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = None
    attempt_no: int | None = Field(default=None, ge=1)
    status: A2aResultStatus | None = None
    output: str | None = None
    artifacts: list[A2aArtifactIn] = Field(default_factory=list)
    endpoint: str | None = None
    pending_tasks: int | None = None
    completed_at: datetime | None = None
    body: str | None = Field(default=None, max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict)


class A2aAckOut(BaseModel):
    message_id: str
    accepted: bool = True
    duplicate: bool = False
