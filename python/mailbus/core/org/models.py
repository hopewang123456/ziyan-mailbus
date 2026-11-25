"""组织上下文的模型。

静态空间（site/floor/room/seat 几何）来自只读种子；
数据库只保存团队、岗位与工位覆盖，避免把空间布局当成可变业务数据。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.org.values import RoomKind


@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    name: str
    leader_employee_id: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Position:
    """岗位；capabilities 是业务技能标签，与登录权限无关。"""

    position_id: str
    name: str
    capabilities: frozenset[str] = frozenset()
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Role:
    """角色；capabilities 是业务技能标签，供派活匹配。"""

    role_id: str
    name: str
    capabilities: frozenset[str] = frozenset()
    description: str | None = None
    enabled: bool = True
    icon: str | None = None
    color: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SeatAssignment:
    """工位覆盖层：几何默认值仍以种子为准，这里只记差异。"""

    seat_id: str
    team_id: str | None = None
    position_id: str | None = None
    x: float | None = None
    y: float | None = None
    rotation: float | None = None


@dataclass(frozen=True, slots=True)
class SeatDef:
    seat_id: str
    x: float
    y: float
    rotation: float = 0.0


@dataclass(frozen=True, slots=True)
class RoomDef:
    room_id: str
    name: str
    kind: RoomKind
    x: float
    y: float
    w: float
    h: float
    seats: tuple[SeatDef, ...] = ()


@dataclass(frozen=True, slots=True)
class FloorDef:
    floor_id: str
    name: str
    level: int
    rooms: tuple[RoomDef, ...] = ()


@dataclass(frozen=True, slots=True)
class LayoutDef:
    site_id: str
    name: str
    org_name: str
    floors: tuple[FloorDef, ...] = ()

    def seats(self) -> tuple[SeatDef, ...]:
        return tuple(seat for floor in self.floors for room in floor.rooms for seat in room.seats)

    def seat_index(self) -> dict[str, SeatDef]:
        return {seat.seat_id: seat for seat in self.seats()}
