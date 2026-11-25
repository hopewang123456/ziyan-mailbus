"""岗位、团队与工位路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import org_admin as mapper
from mailbus.api.schemas.contract.org import (
    BindingIn,
    PositionIn,
    PositionListOut,
    PositionOut,
    SeatAssignIn,
    SeatListOut,
    SeatOut,
    TeamIn,
    TeamListOut,
    TeamOut,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api", tags=["org"])


def _svc(request: Request):
    return request.app.state.container.org_admin.structure


# ---------- 岗位 ----------


@router.get("/positions", response_model=PositionListOut, summary="岗位列表")
def list_positions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PositionListOut:
    get_actor(request)
    items, total = _svc(request).list_positions(limit, offset)
    return PositionListOut(
        items=[mapper.to_position_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/positions", response_model=PositionOut, status_code=201, summary="创建岗位")
@declares(Capability.ORG_MANAGE)
def create_position(payload: PositionIn, request: Request) -> PositionOut:
    return mapper.to_position_out(
        _svc(request).create_position(get_actor(request), payload.name, payload.capabilities)
    )


@router.get("/positions/{position_id}", response_model=PositionOut, summary="岗位详情")
def get_position(position_id: str, request: Request) -> PositionOut:
    return mapper.to_position_out(_svc(request).get_position(position_id))


@router.patch("/positions/{position_id}", response_model=PositionOut, summary="更新岗位")
@declares(Capability.ORG_MANAGE)
def update_position(
    position_id: str, payload: PositionIn, request: Request
) -> PositionOut:
    return mapper.to_position_out(
        _svc(request).update_position(
            get_actor(request), position_id, payload.name, payload.capabilities
        )
    )


@router.delete("/positions/{position_id}", status_code=204, summary="删除岗位")
@declares(Capability.ORG_MANAGE)
def delete_position(position_id: str, request: Request) -> None:
    _svc(request).delete_position(get_actor(request), position_id)


@router.put(
    "/positions/{position_id}/roles", response_model=PositionOut, summary="岗位绑定角色"
)
@declares(Capability.ROLE_BIND)
def bind_position_roles(
    position_id: str, payload: BindingIn, request: Request
) -> PositionOut:
    return mapper.to_position_out(
        _svc(request).bind_position_roles(get_actor(request), position_id, payload.ids)
    )


@router.put(
    "/positions/{position_id}/employees",
    response_model=PositionOut,
    summary="岗位分配员工",
)
@declares(Capability.ORG_MANAGE)
def bind_position_employees(
    position_id: str, payload: BindingIn, request: Request
) -> PositionOut:
    return mapper.to_position_out(
        _svc(request).bind_position_employees(get_actor(request), position_id, payload.ids)
    )


# ---------- 团队 ----------


@router.get("/teams", response_model=TeamListOut, summary="团队列表")
def list_teams(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TeamListOut:
    get_actor(request)
    items, total = _svc(request).list_teams(limit, offset)
    return TeamListOut(
        items=[mapper.to_team_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/teams", response_model=TeamOut, status_code=201, summary="创建团队")
@declares(Capability.ORG_MANAGE)
def create_team(payload: TeamIn, request: Request) -> TeamOut:
    return mapper.to_team_out(
        _svc(request).create_team(
            get_actor(request), payload.name, payload.leader_employee_id
        )
    )


@router.patch("/teams/{team_id}", response_model=TeamOut, summary="更新团队")
@declares(Capability.ORG_MANAGE)
def update_team(team_id: str, payload: TeamIn, request: Request) -> TeamOut:
    return mapper.to_team_out(
        _svc(request).update_team(
            get_actor(request), team_id, payload.name, payload.leader_employee_id
        )
    )


@router.delete("/teams/{team_id}", status_code=204, summary="删除团队")
@declares(Capability.ORG_MANAGE)
def delete_team(team_id: str, request: Request) -> None:
    _svc(request).delete_team(get_actor(request), team_id)


@router.get("/teams/{team_id}/seats", response_model=SeatListOut, summary="团队工位列表")
def list_team_seats(team_id: str, request: Request) -> SeatListOut:
    items = _svc(request).list_team_seats(get_actor(request), team_id)
    return SeatListOut(
        items=[mapper.to_seat_out(item) for item in items],
        total=len(items),
        limit=len(items),
        offset=0,
    )


@router.put("/seats/{seat_id}/assign", response_model=SeatOut, summary="分配工位")
@declares(Capability.ORG_MANAGE)
def assign_seat(seat_id: str, payload: SeatAssignIn, request: Request) -> SeatOut:
    return mapper.to_seat_out(
        _svc(request).assign_seat(
            get_actor(request),
            seat_id,
            payload.employee_id,
            payload.team_id,
            payload.position_id,
        )
    )
