"""技能包的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from mailbus.core.skills.models import SkillBinding, SkillPackage
from mailbus.core.skills.values import SkillSourceType, SkillTargetType


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _package_from_row(row: sqlite3.Row) -> SkillPackage:
    return SkillPackage(
        package_id=row["package_id"],
        name=row["name"],
        source_type=SkillSourceType(row["source_type"]),
        source_uri=row["source_uri"],
        entry=row["entry"],
        version=row["version"],
        enabled=bool(row["enabled"]),
        note=row["note"],
        last_checked_at=_from_epoch(row["last_checked_at"]),
        last_error=row["last_error"],
        created_at=_from_epoch(row["created_at"]),
        updated_at=_from_epoch(row["updated_at"]),
    )


class SqliteSkillPackageRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def get(self, package_id: str) -> SkillPackage | None:
        row = self._conn.execute(
            "SELECT * FROM skills_packages WHERE package_id = ?", (package_id,)
        ).fetchone()
        return None if row is None else _package_from_row(row)

    def save(self, package: SkillPackage) -> None:
        now = package.updated_at or self._clock.now()
        created = package.created_at or now
        self._conn.execute(
            "INSERT INTO skills_packages (package_id, name, source_type, source_uri, entry,"
            " version, enabled, note, last_checked_at, last_error, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (package_id) DO UPDATE SET"
            " name = excluded.name,"
            " source_type = excluded.source_type,"
            " source_uri = excluded.source_uri,"
            " entry = excluded.entry,"
            " version = excluded.version,"
            " enabled = excluded.enabled,"
            " note = excluded.note,"
            " last_checked_at = excluded.last_checked_at,"
            " last_error = excluded.last_error,"
            " updated_at = excluded.updated_at",
            (
                package.package_id,
                package.name,
                package.source_type.value,
                package.source_uri,
                package.entry,
                package.version,
                int(package.enabled),
                package.note,
                _to_epoch(package.last_checked_at)
                if package.last_checked_at
                else None,
                package.last_error,
                _to_epoch(created),
                _to_epoch(now),
            ),
        )

    def delete(self, package_id: str) -> None:
        self._conn.execute(
            "DELETE FROM skills_packages WHERE package_id = ?", (package_id,)
        )

    def list_all(self) -> list[SkillPackage]:
        rows = self._conn.execute(
            "SELECT * FROM skills_packages ORDER BY created_at, package_id"
        ).fetchall()
        return [_package_from_row(row) for row in rows]


def _binding_from_row(row: sqlite3.Row) -> SkillBinding:
    return SkillBinding(
        package_id=row["package_id"],
        target_type=SkillTargetType(row["target_type"]),
        target_id=row["target_id"],
        enabled=bool(row["enabled"]),
        created_at=_from_epoch(row["created_at"]),
    )


class SqliteSkillBindingRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def upsert(self, binding: SkillBinding) -> None:
        self._conn.execute(
            "INSERT INTO skills_bindings (package_id, target_type, target_id, enabled,"
            " created_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (package_id, target_type, target_id) DO UPDATE SET"
            " enabled = excluded.enabled",
            (
                binding.package_id,
                binding.target_type.value,
                binding.target_id,
                int(binding.enabled),
                _to_epoch(binding.created_at or self._clock.now()),
            ),
        )

    def delete(
        self, package_id: str, target_type: SkillTargetType, target_id: str
    ) -> None:
        self._conn.execute(
            "DELETE FROM skills_bindings WHERE package_id = ? AND target_type = ?"
            " AND target_id = ?",
            (package_id, target_type.value, target_id),
        )

    def list_by_target(
        self, target_type: SkillTargetType, target_id: str
    ) -> list[SkillBinding]:
        rows = self._conn.execute(
            "SELECT * FROM skills_bindings WHERE target_type = ? AND target_id = ?"
            " ORDER BY package_id",
            (target_type.value, target_id),
        ).fetchall()
        return [_binding_from_row(row) for row in rows]

    def list_all(self) -> list[SkillBinding]:
        rows = self._conn.execute(
            "SELECT * FROM skills_bindings ORDER BY package_id, target_type, target_id"
        ).fetchall()
        return [_binding_from_row(row) for row in rows]
