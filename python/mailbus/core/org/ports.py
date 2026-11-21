"""组织上下文对外的仓储与种子端口。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.org.models import LayoutDef, Position, SeatAssignment, Team
from mailbus.core.shared.ports import OutboxPort


class TeamRepository(Protocol):
    def create(self, team: Team) -> None:
        """重复 team_id 视为幂等，不覆盖已有名称。"""

    def get(self, team_id: str) -> Team | None: ...

    def list_all(self) -> list[Team]: ...

    def delete(self, team_id: str) -> None: ...


class PositionRepository(Protocol):
    def add(self, position: Position) -> None: ...

    def get(self, position_id: str) -> Position | None: ...

    def list_all(self) -> list[Position]: ...

    def delete(self, position_id: str) -> None: ...


class SeatRepository(Protocol):
    def upsert(self, assignment: SeatAssignment) -> None: ...

    def get(self, seat_id: str) -> SeatAssignment | None: ...

    def list_all(self) -> list[SeatAssignment]: ...


class LayoutSeedPort(Protocol):
    def load(self) -> LayoutDef:
        """读取只读的空间种子；实现负责缓存与结构校验。"""


class OrgUnitOfWork(Protocol):
    outbox: OutboxPort
    teams: TeamRepository
    positions: PositionRepository
    seats: SeatRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
