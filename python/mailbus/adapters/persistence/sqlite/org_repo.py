"""组织上下文的 SQLite 仓储。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from mailbus.core.org.models import Position, SeatAssignment, Team
from mailbus.core.shared.values import Capability


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


class SqliteTeamRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def create(self, team: Team) -> None:
        self._conn.execute(
            "INSERT INTO org_teams (team_id, name, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT (team_id) DO NOTHING",
            (team.team_id, team.name, _to_epoch(self._clock.now())),
        )

    def get(self, team_id: str) -> Team | None:
        row = self._conn.execute(
            "SELECT team_id, name FROM org_teams WHERE team_id = ?", (team_id,)
        ).fetchone()
        return None if row is None else Team(team_id=row["team_id"], name=row["name"])

    def list_all(self) -> list[Team]:
        rows = self._conn.execute(
            "SELECT team_id, name FROM org_teams ORDER BY created_at, team_id"
        )
        return [Team(team_id=row["team_id"], name=row["name"]) for row in rows]

    def delete(self, team_id: str) -> None:
        self._conn.execute("DELETE FROM org_teams WHERE team_id = ?", (team_id,))


class SqlitePositionRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, position: Position) -> None:
        self._conn.execute(
            "INSERT INTO org_positions (position_id, name, capabilities, created_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT (position_id) DO NOTHING",
            (
                position.position_id,
                position.name,
                json.dumps(sorted(cap.value for cap in position.capabilities)),
                _to_epoch(self._clock.now()),
            ),
        )

    def get(self, position_id: str) -> Position | None:
        row = self._conn.execute(
            "SELECT position_id, name, capabilities FROM org_positions WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        return None if row is None else _position_from_row(row)

    def list_all(self) -> list[Position]:
        rows = self._conn.execute(
            "SELECT position_id, name, capabilities FROM org_positions"
            " ORDER BY created_at, position_id"
        )
        return [_position_from_row(row) for row in rows]

    def delete(self, position_id: str) -> None:
        self._conn.execute(
            "DELETE FROM org_positions WHERE position_id = ?", (position_id,)
        )


def _position_from_row(row: sqlite3.Row) -> Position:
    return Position(
        position_id=row["position_id"],
        name=row["name"],
        capabilities=frozenset(Capability(v) for v in json.loads(row["capabilities"])),
    )


class SqliteSeatRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def upsert(self, assignment: SeatAssignment) -> None:
        self._conn.execute(
            "INSERT INTO org_seats (seat_id, team_id, position_id, x, y, rotation, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (seat_id) DO UPDATE SET"
            " team_id = excluded.team_id,"
            " position_id = excluded.position_id,"
            " x = excluded.x,"
            " y = excluded.y,"
            " rotation = excluded.rotation,"
            " updated_at = excluded.updated_at",
            (
                assignment.seat_id,
                assignment.team_id,
                assignment.position_id,
                assignment.x,
                assignment.y,
                assignment.rotation,
                _to_epoch(self._clock.now()),
            ),
        )

    def get(self, seat_id: str) -> SeatAssignment | None:
        row = self._conn.execute(
            "SELECT * FROM org_seats WHERE seat_id = ?", (seat_id,)
        ).fetchone()
        return None if row is None else _assignment_from_row(row)

    def list_all(self) -> list[SeatAssignment]:
        rows = self._conn.execute("SELECT * FROM org_seats ORDER BY seat_id")
        return [_assignment_from_row(row) for row in rows]


def _assignment_from_row(row: sqlite3.Row) -> SeatAssignment:
    return SeatAssignment(
        seat_id=row["seat_id"],
        team_id=row["team_id"],
        position_id=row["position_id"],
        x=row["x"],
        y=row["y"],
        rotation=row["rotation"],
    )
