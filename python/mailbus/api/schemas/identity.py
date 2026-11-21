"""identity 分组的对外模型（wire 契约）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from mailbus.core.shared.values import Capability

AccountTypeIn = Literal["human", "agent"]
DataScopeIn = Literal["self", "team", "global"]


class BootstrapStepOut(BaseModel):
    step: str
    done: bool
    skippable: bool


class BootstrapStatusOut(BaseModel):
    steps: list[BootstrapStepOut]
    completed: bool


class EmployeeOut(BaseModel):
    employee_id: str
    display_name: str
    account_type: str
    status: str
    team_id: str | None = None
    position_id: str | None = None
    seat_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    agent_framework: str | None = None
    capabilities: list[str]
    data_scope: str
    file_scope: list[str]
    endpoint: str | None = None
    endpoint_approved: bool
    last_heartbeat: datetime | None = None


class SessionOut(BaseModel):
    employee: EmployeeOut
    token: str


class ApplyOut(BaseModel):
    employee: EmployeeOut
    token: str | None = None


class InviteOut(BaseModel):
    invite_code: str
    account_type: str
    team_id: str | None = None
    position_id: str | None = None
    data_scope: str
    capabilities: list[str]
    expires_at: datetime | None = None


class TeamOut(BaseModel):
    team_id: str
    name: str


class SuperAdminIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    employee_id: str | None = None


class ModelConfigIn(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    api_base: str | None = None


class ApplyIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    account_type: AccountTypeIn
    invite_code: str | None = None
    endpoint: str | None = None
    seat_id: str | None = None
    agent_id: str | None = None


class ReviewIn(BaseModel):
    approved: bool
    note: str | None = None


class DeregisterIn(BaseModel):
    reason: str = ""


class SeatAssignIn(BaseModel):
    seat_id: str | None = None


class AgentBindIn(BaseModel):
    agent_id: str | None = None


class EndpointReviewIn(BaseModel):
    """端点补录与审核：可只写地址、只改审核状态，或同时提交。"""

    approved: bool | None = None
    endpoint: str | None = None


class ManagerIn(BaseModel):
    enabled: bool


class InviteIn(BaseModel):
    account_type: AccountTypeIn
    team_id: str | None = None
    position_id: str | None = None
    capabilities: list[Capability] = Field(default_factory=list)
    data_scope: DataScopeIn = "self"
    expires_in_hours: int = Field(default=72, ge=0, le=720)
