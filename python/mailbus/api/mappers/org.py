"""org 协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.org import (
    OrgSeatOut,
    PositionIn,
    PositionOut,
    SeatUpdateIn,
    TeamIn,
    TeamOut,
)
from mailbus.application.org.dto import (
    PositionCommand,
    PositionView,
    SeatCommand,
    SeatView,
    TeamCommand,
    TeamView,
    make_position_command,
    make_seat_command,
    make_team_command,
)


def to_team_out(view: TeamView) -> TeamOut:
    return TeamOut(team_id=view.team_id, name=view.name)


def to_position_out(view: PositionView) -> PositionOut:
    return PositionOut(
        position_id=view.position_id,
        name=view.name,
        capabilities=list(view.capabilities),
    )


def to_seat_out(view: SeatView) -> OrgSeatOut:
    return OrgSeatOut(
        seat_id=view.seat_id,
        floor_id=view.floor_id,
        room_id=view.room_id,
        x=view.x,
        y=view.y,
        rotation=view.rotation,
        team_id=view.team_id,
        position_id=view.position_id,
    )


def team_command(payload: TeamIn) -> TeamCommand:
    return make_team_command(name=payload.name, team_id=payload.team_id)


def position_command(payload: PositionIn) -> PositionCommand:
    return make_position_command(
        name=payload.name,
        capabilities=tuple(payload.capabilities),
        position_id=payload.position_id,
    )


def seat_command(payload: SeatUpdateIn) -> SeatCommand:
    return make_seat_command(
        team_id=payload.team_id,
        position_id=payload.position_id,
        x=payload.x,
        y=payload.y,
        rotation=payload.rotation,
    )
