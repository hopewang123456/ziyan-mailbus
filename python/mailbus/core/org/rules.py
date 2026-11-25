"""组织上下文的纯函数规则。"""

from __future__ import annotations

from datetime import datetime

from mailbus.core.org.models import Position, SeatAssignment, Team
from mailbus.core.shared.errors import InvalidStateError
from mailbus.core.shared.events import DomainEvent


def validate_name(value: str, label: str) -> str:
    name = value.strip()
    if not name:
        raise InvalidStateError(f"{label}不能为空")
    if len(name) > 64:
        raise InvalidStateError(f"{label}不能超过 64 个字符")
    return name


def create_team(
    team_id: str,
    name: str,
    now: datetime,
    leader_employee_id: str | None = None,
) -> tuple[Team, tuple[DomainEvent, ...]]:
    team = Team(
        team_id=team_id,
        name=validate_name(name, "团队名称"),
        leader_employee_id=leader_employee_id,
        created_at=now,
    )
    event = DomainEvent(
        kind="org.team_created",
        payload={"team_id": team.team_id, "name": team.name, "at": now.isoformat()},
    )
    return team, (event,)


def create_position(
    position_id: str,
    name: str,
    capabilities: frozenset[str],
    now: datetime,
) -> tuple[Position, tuple[DomainEvent, ...]]:
    position = Position(
        position_id=position_id,
        name=validate_name(name, "岗位名称"),
        capabilities=capabilities,
        created_at=now,
    )
    event = DomainEvent(
        kind="org.position_created",
        payload={"position_id": position.position_id, "at": now.isoformat()},
    )
    return position, (event,)


def delete_team(team: Team, now: datetime) -> tuple[DomainEvent, ...]:
    return (
        DomainEvent(
            kind="org.team_deleted",
            payload={"team_id": team.team_id, "at": now.isoformat()},
        ),
    )


def delete_position(position: Position, now: datetime) -> tuple[DomainEvent, ...]:
    return (
        DomainEvent(
            kind="org.position_deleted",
            payload={"position_id": position.position_id, "at": now.isoformat()},
        ),
    )


def merge_seat(
    seat_id: str,
    *,
    team_id: str | None,
    position_id: str | None,
    x: float | None,
    y: float | None,
    rotation: float | None,
) -> SeatAssignment:
    """覆盖层只保存显式给出的字段，None 表示沿用种子几何。"""
    return SeatAssignment(
        seat_id=seat_id,
        team_id=team_id,
        position_id=position_id,
        x=x,
        y=y,
        rotation=rotation,
    )
