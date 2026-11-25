"""员工目录路由：列表、邀请、更新、软删除、权限/角色/技能与脱敏选项。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import org_admin as mapper
from mailbus.api.schemas.contract.org import (
    CapabilitiesIn,
    CapabilitiesOut,
    EmployeeInviteIn,
    EmployeeListOut,
    EmployeeUpdateIn,
    InviteOut,
    OptionListOut,
    PermissionsIn,
    PermissionsOut,
    RolesIn,
    RolesOut,
)
from mailbus.api.schemas.identity import EmployeeOut
from mailbus.application.org.dto import OptionView
from mailbus.core.shared.values import Capability as Cap
from mailbus.core.shared.values import DataScope

router = APIRouter(prefix="/api", tags=["org"])


def _svc(request: Request):
    return request.app.state.container.org_admin


@router.get("/employees", response_model=EmployeeListOut, summary="员工列表")
def list_employees(
    request: Request,
    type: Literal["human", "agent"] | None = None,
    position_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> EmployeeListOut:
    items, total = _svc(request).employees.list(
        get_actor(request), type, position_id, limit, offset
    )
    return EmployeeListOut(
        items=[mapper.employee_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/employees/invite", response_model=InviteOut, summary="邀请真人")
@declares(Cap.EMPLOYEE_INVITE)
def invite_employee(payload: EmployeeInviteIn, request: Request) -> InviteOut:
    view = _svc(request).invites.issue(
        get_actor(request),
        payload.display_name,
        payload.position_id,
        payload.team_id,
        DataScope(payload.data_scope),
        payload.permissions,
        payload.expires_in_hours,
    )
    return mapper.to_invite_out(view)


@router.get("/employees/{employee_id}", response_model=EmployeeOut, summary="员工详情")
def get_employee(employee_id: str, request: Request) -> EmployeeOut:
    return mapper.employee_out(_svc(request).employees.get(get_actor(request), employee_id))


@router.patch("/employees/{employee_id}", response_model=EmployeeOut, summary="更新员工")
@declares(Cap.ORG_MANAGE)
def update_employee(
    employee_id: str, payload: EmployeeUpdateIn, request: Request
) -> EmployeeOut:
    changes = payload.model_dump(exclude_unset=True)
    view = _svc(request).employees.update(get_actor(request), employee_id, changes)
    return mapper.employee_out(view)


@router.delete("/employees/{employee_id}", status_code=204, summary="软删除员工")
@declares(Cap.EMPLOYEE_REMOVE)
def delete_employee(employee_id: str, request: Request) -> None:
    _svc(request).employees.delete(get_actor(request), employee_id)


@router.get(
    "/employees/{employee_id}/permissions",
    response_model=PermissionsOut,
    summary="读取员工权限",
)
def get_permissions(employee_id: str, request: Request) -> PermissionsOut:
    values = _svc(request).employees.permissions(get_actor(request), employee_id)
    return mapper.to_permissions_out(employee_id, values)


@router.put(
    "/employees/{employee_id}/permissions",
    response_model=PermissionsOut,
    summary="覆盖员工权限",
)
@declares(Cap.CONSOLE_ADMIN)
def put_permissions(
    employee_id: str, payload: PermissionsIn, request: Request
) -> PermissionsOut:
    values = _svc(request).employees.set_permissions(
        get_actor(request), employee_id, payload.permissions
    )
    return mapper.to_permissions_out(employee_id, values)


@router.get(
    "/employees/{employee_id}/roles", response_model=RolesOut, summary="读取员工角色"
)
def get_employee_roles(employee_id: str, request: Request) -> RolesOut:
    values = _svc(request).employees.roles(get_actor(request), employee_id)
    return mapper.to_roles_out(employee_id, values)


@router.put(
    "/employees/{employee_id}/roles", response_model=RolesOut, summary="覆盖员工角色"
)
@declares(Cap.ROLE_BIND)
def put_employee_roles(
    employee_id: str, payload: RolesIn, request: Request
) -> RolesOut:
    values = _svc(request).employees.set_roles(
        get_actor(request), employee_id, payload.role_ids
    )
    return mapper.to_roles_out(employee_id, values)


@router.get(
    "/employees/{employee_id}/capabilities",
    response_model=CapabilitiesOut,
    summary="读取员工业务技能",
)
def get_capabilities(employee_id: str, request: Request) -> CapabilitiesOut:
    values = _svc(request).employees.capabilities(get_actor(request), employee_id)
    return mapper.to_capabilities_out(employee_id, values)


@router.put(
    "/employees/{employee_id}/capabilities",
    response_model=CapabilitiesOut,
    summary="覆盖员工业务技能",
)
@declares(Cap.ROLE_BIND)
def put_capabilities(
    employee_id: str, payload: CapabilitiesIn, request: Request
) -> CapabilitiesOut:
    values = _svc(request).employees.set_capabilities(
        get_actor(request), employee_id, payload.capabilities
    )
    return mapper.to_capabilities_out(employee_id, values)


@router.get("/options/employees", response_model=OptionListOut, summary="脱敏员工选项")
def employee_options(
    request: Request,
    position_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> OptionListOut:
    items, total = _svc(request).employees.options(
        get_actor(request), position_id, limit, offset
    )
    return OptionListOut(
        items=[mapper.to_option_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/options/positions", response_model=OptionListOut, summary="脱敏岗位选项")
def position_options(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> OptionListOut:
    positions, _ = _svc(request).structure.list_positions(10_000, 0)
    page = positions[offset : offset + limit]
    return OptionListOut(
        items=[
            mapper.to_option_out(
                OptionView(option_id=item.position_id, label=item.name)
            )
            for item in page
        ],
        total=len(positions),
        limit=limit,
        offset=offset,
    )
