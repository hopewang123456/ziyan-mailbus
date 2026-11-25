"""identity 分组的对外模型（wire 契约）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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
    permissions: list[str]
    data_scope: str
    file_scope: list[str]
    endpoint: str | None = None
    endpoint_approved: bool
    last_heartbeat: datetime | None = None


class SessionOut(BaseModel):
    employee: EmployeeOut
    token: str


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
