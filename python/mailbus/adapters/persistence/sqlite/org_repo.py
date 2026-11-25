"""组织上下文的 SQLite 仓储。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from mailbus.core.org.models import Position, Role, SeatAssignment, Team


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _tags(value: str | None) -> frozenset[str]:
    return frozenset(json.loads(value or "[]"))


class SqliteTeamRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def create(self, team: Team) -> None:
        self._conn.execute(
            "INSERT INTO org_teams (team_id, name, leader_employee_id, created_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT (team_id) DO NOTHING",
            (
                team.team_id,
                team.name,
                team.leader_employee_id,
                _to_epoch(team.created_at or self._clock.now()),
            ),
        )

    def update(self, team: Team) -> None:
        self._conn.execute(
            "UPDATE org_teams SET name = ?, leader_employee_id = ? WHERE team_id = ?",
            (team.name, team.leader_employee_id, team.team_id),
        )

    def get(self, team_id: str) -> Team | None:
        row = self._conn.execute(
            "SELECT * FROM org_teams WHERE team_id = ?", (team_id,)
        ).fetchone()
        return None if row is None else _team_from_row(row)

    def list_all(self) -> list[Team]:
        rows = self._conn.execute(
            "SELECT * FROM org_teams ORDER BY created_at, team_id"
        ).fetchall()
        return [_team_from_row(row) for row in rows]

    def delete(self, team_id: str) -> None:
        self._conn.execute("DELETE FROM org_teams WHERE team_id = ?", (team_id,))


def _team_from_row(row: sqlite3.Row) -> Team:
    return Team(
        team_id=row["team_id"],
        name=row["name"],
        leader_employee_id=row["leader_employee_id"],
        created_at=_from_epoch(row["created_at"]),
    )


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
                json.dumps(sorted(position.capabilities), ensure_ascii=False),
                _to_epoch(position.created_at or self._clock.now()),
            ),
        )

    def update(self, position: Position) -> None:
        self._conn.execute(
            "UPDATE org_positions SET name = ?, capabilities = ? WHERE position_id = ?",
            (
                position.name,
                json.dumps(sorted(position.capabilities), ensure_ascii=False),
                position.position_id,
            ),
        )

    def get(self, position_id: str) -> Position | None:
        row = self._conn.execute(
            "SELECT * FROM org_positions WHERE position_id = ?", (position_id,)
        ).fetchone()
        return None if row is None else _position_from_row(row)

    def list_all(self) -> list[Position]:
        rows = self._conn.execute(
            "SELECT * FROM org_positions ORDER BY created_at, position_id"
        ).fetchall()
        return [_position_from_row(row) for row in rows]

    def delete(self, position_id: str) -> None:
        self._conn.execute(
            "DELETE FROM org_positions WHERE position_id = ?", (position_id,)
        )
        self._conn.execute(
            "DELETE FROM position_role_bindings WHERE position_id = ?", (position_id,)
        )


def _position_from_row(row: sqlite3.Row) -> Position:
    return Position(
        position_id=row["position_id"],
        name=row["name"],
        capabilities=_tags(row["capabilities"]),
        created_at=_from_epoch(row["created_at"]),
    )


class SqliteRoleRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, role: Role) -> None:
        now = self._clock.now()
        self._conn.execute(
            "INSERT INTO agent_roles (role_id, role_name, capabilities, description,"
            " enabled, icon, color, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                role.role_id,
                role.name,
                json.dumps(sorted(role.capabilities), ensure_ascii=False),
                role.description,
                int(role.enabled),
                role.icon,
                role.color,
                _to_epoch(role.created_at or now),
                _to_epoch(role.updated_at or now),
            ),
        )

    def update(self, role: Role) -> None:
        self._conn.execute(
            "UPDATE agent_roles SET role_name = ?, capabilities = ?, description = ?,"
            " enabled = ?, icon = ?, color = ?, updated_at = ? WHERE role_id = ?",
            (
                role.name,
                json.dumps(sorted(role.capabilities), ensure_ascii=False),
                role.description,
                int(role.enabled),
                role.icon,
                role.color,
                _to_epoch(role.updated_at or self._clock.now()),
                role.role_id,
            ),
        )

    def get(self, role_id: str) -> Role | None:
        row = self._conn.execute(
            "SELECT * FROM agent_roles WHERE role_id = ?", (role_id,)
        ).fetchone()
        return None if row is None else _role_from_row(row)

    def list_all(self) -> list[Role]:
        rows = self._conn.execute(
            "SELECT * FROM agent_roles ORDER BY created_at, role_id"
        ).fetchall()
        return [_role_from_row(row) for row in rows]

    def delete(self, role_id: str) -> None:
        self._conn.execute("DELETE FROM agent_roles WHERE role_id = ?", (role_id,))
        self._conn.execute(
            "DELETE FROM employee_role_bindings WHERE role_id = ?", (role_id,)
        )
        self._conn.execute(
            "DELETE FROM position_role_bindings WHERE role_id = ?", (role_id,)
        )

    def position_ids(self, role_id: str) -> list[str]:
        return self._ids("position_role_bindings", "position_id", "role_id", role_id)

    def employee_ids(self, role_id: str) -> list[str]:
        return self._ids("employee_role_bindings", "employee_id", "role_id", role_id)

    def set_positions(self, role_id: str, position_ids: list[str]) -> None:
        self._replace("position_role_bindings", "role_id", role_id, "position_id", position_ids)

    def set_employees(self, role_id: str, employee_ids: list[str]) -> None:
        self._replace("employee_role_bindings", "role_id", role_id, "employee_id", employee_ids)

    def role_ids_for_position(self, position_id: str) -> list[str]:
        return self._ids(
            "position_role_bindings", "role_id", "position_id", position_id
        )

    def role_ids_for_employee(self, employee_id: str) -> list[str]:
        return self._ids(
            "employee_role_bindings", "role_id", "employee_id", employee_id
        )

    def set_roles_for_position(self, position_id: str, role_ids: list[str]) -> None:
        self._replace(
            "position_role_bindings", "position_id", position_id, "role_id", role_ids
        )

    def set_roles_for_employee(self, employee_id: str, role_ids: list[str]) -> None:
        self._replace(
            "employee_role_bindings", "employee_id", employee_id, "role_id", role_ids
        )

    def _ids(self, table: str, column: str, key: str, value: str) -> list[str]:
        rows = self._conn.execute(
            f"SELECT {column} FROM {table} WHERE {key} = ? ORDER BY {column}",
            (value,),
        ).fetchall()
        return [row[0] for row in rows]

    def _replace(
        self, table: str, key: str, value: str, column: str, targets: list[str]
    ) -> None:
        # 表/列名只来自本类常量，不接受外部输入。
        self._conn.execute(f"DELETE FROM {table} WHERE {key} = ?", (value,))
        self._conn.executemany(
            f"INSERT OR IGNORE INTO {table} ({key}, {column}) VALUES (?, ?)",
            [(value, target) for target in dict.fromkeys(targets)],
        )


def _role_from_row(row: sqlite3.Row) -> Role:
    return Role(
        role_id=row["role_id"],
        name=row["role_name"],
        capabilities=_tags(row["capabilities"]),
        description=row["description"],
        enabled=bool(row["enabled"]),
        icon=row["icon"],
        color=row["color"],
        created_at=_from_epoch(row["created_at"]),
        updated_at=_from_epoch(row["updated_at"]),
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
