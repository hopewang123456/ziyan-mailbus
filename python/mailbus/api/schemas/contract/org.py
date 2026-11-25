"""组织域契约模型：员工、岗位、角色、团队、工位、选项与邀请。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from mailbus.api.schemas.contract.common import Page
from mailbus.api.schemas.identity import EmployeeOut

DataScopeIn = Literal["self", "team", "global"]


class EmployeeListOut(Page[EmployeeOut]):
    pass


class EmployeeUpdateIn(BaseModel):
    """PATCH 语义：只提交需要修改的字段。"""

    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    team_id: str | None = None
    position_id: str | None = None
    seat_id: str | None = None
    data_scope: DataScopeIn | None = None
    enabled: bool | None = None


class EmployeeInviteIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    position_id: str | None = None
    team_id: str | None = None
    data_scope: DataScopeIn = "self"
    permissions: list[str] = Field(default_factory=list)
    expires_in_hours: int = Field(default=24, ge=1, le=720)


class InviteOut(BaseModel):
    invite_id: str
    invite_code: str | None = Field(default=None, description="明文仅创建/重发响应返回一次")
    account_type: str
    team_id: str | None = None
    position_id: str | None = None
    data_scope: str
    permissions: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None


class InviteAcceptIn(BaseModel):
    invite_code: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)


class InviteAcceptOut(BaseModel):
    employee: EmployeeOut
    token: str | None = None


class PermissionsIn(BaseModel):
    permissions: list[str] = Field(default_factory=list)


class PermissionsOut(BaseModel):
    employee_id: str
    permissions: list[str]


class RolesIn(BaseModel):
    role_ids: list[str] = Field(default_factory=list)


class RolesOut(BaseModel):
    employee_id: str
    role_ids: list[str]


class CapabilitiesIn(BaseModel):
    capabilities: list[str] = Field(default_factory=list)


class CapabilitiesOut(BaseModel):
    employee_id: str
    capabilities: list[str]


class PositionIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    capabilities: list[str] = Field(default_factory=list)


class PositionOut(BaseModel):
    position_id: str
    name: str
    capabilities: list[str]
    role_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class PositionListOut(Page[PositionOut]):
    pass


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    capabilities: list[str] = Field(default_factory=list)
    description: str | None = None
    enabled: bool = True
    icon: str | None = None
    color: str | None = None


class RoleOut(BaseModel):
    role_id: str
    name: str
    capabilities: list[str]
    description: str | None = None
    enabled: bool
    icon: str | None = None
    color: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoleListOut(Page[RoleOut]):
    pass


class BindingIn(BaseModel):
    """岗位/角色/员工三类绑定共用：提交完整目标集合，服务端按集合覆盖。"""

    ids: list[str] = Field(default_factory=list)


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    leader_employee_id: str | None = None


class TeamOut(BaseModel):
    team_id: str
    name: str
    leader_employee_id: str | None = None
    created_at: datetime | None = None


class TeamListOut(Page[TeamOut]):
    pass


class SeatOut(BaseModel):
    seat_id: str
    team_id: str | None = None
    position_id: str | None = None
    employee_id: str | None = None
    agent_id: str | None = None
    x: float | None = None
    y: float | None = None
    rotation: float | None = None


class SeatListOut(Page[SeatOut]):
    pass


class SeatAssignIn(BaseModel):
    employee_id: str | None = None
    team_id: str | None = None
    position_id: str | None = None


class OptionOut(BaseModel):
    """脱敏下拉项：不含登录名、联系方式、权限与审计字段。"""

    option_id: str
    label: str
    enabled: bool = True


class OptionListOut(Page[OptionOut]):
    pass
