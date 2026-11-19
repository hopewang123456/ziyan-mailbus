"""org 路由：团队、岗位与工位覆盖。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import org as mapper
from mailbus.api.schemas.org import (
    OrgSeatOut,
    PositionIn,
    PositionOut,
    SeatUpdateIn,
    TeamIn,
    TeamOut,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/org", tags=["org"])


def _org(request: Request):
    return request.app.state.container.org


def _require_login(request: Request) -> None:
    get_actor(request)


@router.get("/teams", response_model=list[TeamOut], summary="团队列表")
def list_teams(request: Request) -> list[TeamOut]:
    _require_login(request)
    return [mapper.to_team_out(view) for view in _org(request).list_teams()]


@router.post("/teams", response_model=TeamOut, status_code=201, summary="创建团队")
@declares(Capability.ORG_MANAGE)
def create_team(payload: TeamIn, request: Request) -> TeamOut:
    view = _org(request).create_team(get_actor(request), mapper.team_command(payload))
    return mapper.to_team_out(view)


@router.get("/positions", response_model=list[PositionOut], summary="岗位列表")
def list_positions(request: Request) -> list[PositionOut]:
    _require_login(request)
    views = _org(request).list_positions()
    return [mapper.to_position_out(view) for view in views]


@router.post("/positions", response_model=PositionOut, status_code=201, summary="创建岗位")
@declares(Capability.ORG_MANAGE)
def create_position(payload: PositionIn, request: Request) -> PositionOut:
    view = _org(request).create_position(get_actor(request), mapper.position_command(payload))
    return mapper.to_position_out(view)


@router.get("/seats", response_model=list[OrgSeatOut], summary="工位列表")
def list_seats(request: Request) -> list[OrgSeatOut]:
    _require_login(request)
    return [mapper.to_seat_out(view) for view in _org(request).list_seats()]


@router.patch("/seats/{seat_id}", response_model=OrgSeatOut, summary="更新工位归属")
@declares(Capability.ORG_MANAGE)
def update_seat(seat_id: str, payload: SeatUpdateIn, request: Request) -> OrgSeatOut:
    view = _org(request).update_seat(get_actor(request), seat_id, mapper.seat_command(payload))
    return mapper.to_seat_out(view)
