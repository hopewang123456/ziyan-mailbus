"""组织用例的输入/输出模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.org.models import Position, SeatAssignment, SeatDef, Team
from mailbus.core.shared.values import Capability


@dataclass(frozen=True, slots=True)
class TeamView:
    team_id: str
    name: str

    @classmethod
    def of(cls, team: Team) -> "TeamView":
        return cls(team_id=team.team_id, name=team.name)


@dataclass(frozen=True, slots=True)
class PositionView:
    position_id: str
    name: str
    capabilities: tuple[str, ...]

    @classmethod
    def of(cls, position: Position) -> "PositionView":
        return cls(
            position_id=position.position_id,
            name=position.name,
            capabilities=tuple(sorted(cap.value for cap in position.capabilities)),
        )


@dataclass(frozen=True, slots=True)
class SeatView:
    seat_id: str
    floor_id: str
    room_id: str
    x: float
    y: float
    rotation: float
    team_id: str | None
    position_id: str | None


@dataclass(frozen=True, slots=True)
class TeamCommand:
    name: str
    team_id: str | None = None


@dataclass(frozen=True, slots=True)
class PositionCommand:
    name: str
    capabilities: tuple[Capability, ...] = ()
    position_id: str | None = None


@dataclass(frozen=True, slots=True)
class SeatCommand:
    team_id: str | None = None
    position_id: str | None = None
    x: float | None = None
    y: float | None = None
    rotation: float | None = None


@dataclass(frozen=True, slots=True)
class SeatAgentView:
    """布局里的员工投影（字段名与前端 types.ts 一致）。

    agent_id 沿用员工的稳定键；bound_agent_id 才是 Agent 台账 id。
    """

    agent_id: str
    display_name: str
    position: str
    team: str
    status: str
    task: str
    last_heartbeat: str
    bound_agent_id: str = ""
    agent_name: str = ""
    agent_framework: str = ""
    task_id: str = ""
    task_state: str = ""
    current_node: str = ""
    node_state: str = ""
    progress_done: int = 0
    progress_total: int = 0


@dataclass(frozen=True, slots=True)
class LayoutSeatView:
    seat_id: str
    x: float
    y: float
    rotation: float
    agent: SeatAgentView | None


@dataclass(frozen=True, slots=True)
class LayoutRoomView:
    room_id: str
    name: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    seats: tuple[LayoutSeatView, ...]


@dataclass(frozen=True, slots=True)
class LayoutFloorView:
    floor_id: str
    name: str
    level: int
    rooms: tuple[LayoutRoomView, ...]


@dataclass(frozen=True, slots=True)
class OfficeSiteView:
    site_id: str
    name: str
    org_name: str
    floors: tuple[LayoutFloorView, ...]


def team_view(team: Team) -> TeamView:
    return TeamView.of(team)


def position_view(position: Position) -> PositionView:
    return PositionView.of(position)


def seat_view(
    floor_id: str,
    room_id: str,
    seat: SeatDef,
    assignment: SeatAssignment | None,
) -> SeatView:
    """种子几何 + 覆盖层合并：覆盖字段优先。"""
    return SeatView(
        seat_id=seat.seat_id,
        floor_id=floor_id,
        room_id=room_id,
        x=assignment.x if assignment and assignment.x is not None else seat.x,
        y=assignment.y if assignment and assignment.y is not None else seat.y,
        rotation=(
            assignment.rotation
            if assignment and assignment.rotation is not None
            else seat.rotation
        ),
        team_id=assignment.team_id if assignment else None,
        position_id=assignment.position_id if assignment else None,
    )


def make_team_command(name: str, team_id: str | None = None) -> TeamCommand:
    return TeamCommand(name=name, team_id=team_id)


def make_position_command(
    name: str,
    capabilities: tuple[Capability, ...] = (),
    position_id: str | None = None,
) -> PositionCommand:
    return PositionCommand(name=name, capabilities=capabilities, position_id=position_id)


def make_seat_command(
    team_id: str | None = None,
    position_id: str | None = None,
    x: float | None = None,
    y: float | None = None,
    rotation: float | None = None,
) -> SeatCommand:
    return SeatCommand(
        team_id=team_id, position_id=position_id, x=x, y=y, rotation=rotation
    )


def heartbeat_text(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
