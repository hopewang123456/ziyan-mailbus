"""角色路由：CRUD 与岗位/员工双向绑定。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import org_admin as mapper
from mailbus.api.schemas.contract.org import (
    BindingIn,
    RoleIn,
    RoleListOut,
    RoleOut,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api", tags=["org"])


def _svc(request: Request):
    return request.app.state.container.org_admin.roles


@router.get("/roles", response_model=RoleListOut, summary="角色列表")
def list_roles(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RoleListOut:
    items, total = _svc(request).list_roles(limit, offset)
    return RoleListOut(
        items=[mapper.to_role_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/roles", response_model=RoleOut, status_code=201, summary="创建角色")
@declares(Capability.ROLE_MANAGE)
def create_role(payload: RoleIn, request: Request) -> RoleOut:
    return mapper.to_role_out(
        _svc(request).create(get_actor(request), payload.model_dump())
    )


@router.patch("/roles/{role_id}", response_model=RoleOut, summary="更新角色")
@declares(Capability.ROLE_MANAGE)
def update_role(role_id: str, payload: RoleIn, request: Request) -> RoleOut:
    return mapper.to_role_out(
        _svc(request).update(get_actor(request), role_id, payload.model_dump())
    )


@router.delete("/roles/{role_id}", status_code=204, summary="删除角色")
@declares(Capability.ROLE_MANAGE)
def delete_role(role_id: str, request: Request) -> None:
    _svc(request).delete(get_actor(request), role_id)


@router.put("/roles/{role_id}/positions", response_model=RoleOut, summary="角色绑定岗位")
@declares(Capability.ROLE_BIND)
def bind_role_positions(
    role_id: str, payload: BindingIn, request: Request
) -> RoleOut:
    return mapper.to_role_out(
        _svc(request).bind_role_positions(get_actor(request), role_id, payload.ids)
    )


@router.put("/roles/{role_id}/employees", response_model=RoleOut, summary="角色绑定员工")
@declares(Capability.ROLE_BIND)
def bind_role_employees(
    role_id: str, payload: BindingIn, request: Request
) -> RoleOut:
    return mapper.to_role_out(
        _svc(request).bind_role_employees(get_actor(request), role_id, payload.ids)
    )
