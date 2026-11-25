"""组织管理契约映射：应用层视图 → wire DTO。"""

from __future__ import annotations

from mailbus.api.mappers.identity import to_employee_out
from mailbus.api.schemas.contract.org import (
    CapabilitiesOut,
    InviteOut,
    OptionOut,
    PermissionsOut,
    PositionOut,
    RoleOut,
    RolesOut,
    SeatOut,
    TeamOut,
)
from mailbus.application.org.dto import (
    ContractSeatView,
    OptionView,
    PositionView,
    RoleView,
    TeamView,
)
from mailbus.application.org.invite_views import AdminInviteView


def to_invite_out(view: AdminInviteView) -> InviteOut:
    return InviteOut(
        invite_id=view.invite_id,
        invite_code=view.invite_code,
        account_type=view.account_type,
        team_id=view.team_id,
        position_id=view.position_id,
        data_scope=view.data_scope,
        permissions=list(view.permissions),
        created_by=view.created_by,
        created_at=view.created_at,
        expires_at=view.expires_at,
        consumed_at=view.consumed_at,
        revoked_at=view.revoked_at,
    )


def to_permissions_out(employee_id: str, values: tuple[str, ...]) -> PermissionsOut:
    return PermissionsOut(employee_id=employee_id, permissions=list(values))


def to_roles_out(employee_id: str, values: tuple[str, ...]) -> RolesOut:
    return RolesOut(employee_id=employee_id, role_ids=list(values))


def to_capabilities_out(
    employee_id: str, values: tuple[str, ...]
) -> CapabilitiesOut:
    return CapabilitiesOut(employee_id=employee_id, capabilities=list(values))


def to_position_out(view: PositionView) -> PositionOut:
    return PositionOut(
        position_id=view.position_id,
        name=view.name,
        capabilities=list(view.capabilities),
        role_ids=list(view.role_ids),
        created_at=view.created_at,
    )


def to_role_out(view: RoleView) -> RoleOut:
    return RoleOut(
        role_id=view.role_id,
        name=view.name,
        capabilities=list(view.capabilities),
        description=view.description,
        enabled=view.enabled,
        icon=view.icon,
        color=view.color,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def to_team_out(view: TeamView) -> TeamOut:
    return TeamOut(
        team_id=view.team_id,
        name=view.name,
        leader_employee_id=view.leader_employee_id,
        created_at=view.created_at,
    )


def to_seat_out(view: ContractSeatView) -> SeatOut:
    return SeatOut(
        seat_id=view.seat_id,
        team_id=view.team_id,
        position_id=view.position_id,
        employee_id=view.employee_id,
        agent_id=view.agent_id,
        x=view.x,
        y=view.y,
        rotation=view.rotation,
    )


def to_option_out(view: OptionView) -> OptionOut:
    return OptionOut(option_id=view.option_id, label=view.label, enabled=view.enabled)


employee_out = to_employee_out
