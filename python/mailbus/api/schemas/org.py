"""org 分组的对外模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from mailbus.core.shared.values import Capability


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    team_id: str | None = None


class TeamOut(BaseModel):
    team_id: str
    name: str


class PositionIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    capabilities: list[Capability] = Field(default_factory=list)
    position_id: str | None = None


class PositionOut(BaseModel):
    position_id: str
    name: str
    capabilities: list[str]


class OrgSeatOut(BaseModel):
    seat_id: str
    floor_id: str
    room_id: str
    x: float
    y: float
    rotation: float
    team_id: str | None = None
    position_id: str | None = None


class SeatUpdateIn(BaseModel):
    team_id: str | None = None
    position_id: str | None = None
    x: float | None = None
    y: float | None = None
    rotation: float | None = None
