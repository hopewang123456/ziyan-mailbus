"""协同上下文的 SQLite 仓储：大屏与结对。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlite3 import Connection, Row

from mailbus.core.collab.models import Pair, Screen


def _dt(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _epoch(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp()


def _json(value: object) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(str(value))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class SqliteScreenRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def list_page(self, limit: int, offset: int) -> list[Screen]:
        rows = self._conn.execute(
            "SELECT * FROM collab_screens"
            " ORDER BY COALESCE(last_seen_at, created_at) DESC, screen_id"
            " LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._map(row) for row in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS total FROM collab_screens").fetchone()
        return int(row["total"]) if row else 0

    def list_all(self, limit: int | None = None) -> list[Screen]:
        sql = (
            "SELECT * FROM collab_screens"
            " ORDER BY COALESCE(last_seen_at, created_at) DESC, screen_id"
        )
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._map(row) for row in rows]

    def get(self, screen_id: str) -> Screen | None:
        row = self._conn.execute(
            "SELECT * FROM collab_screens WHERE screen_id = ?", (screen_id,)
        ).fetchone()
        return None if row is None else self._map(row)

    def save(self, screen: Screen) -> None:
        self._conn.execute(
            """
            INSERT INTO collab_screens
                (screen_id, name, online, last_seen_at, created_at, secret_hash,
                 source, config_json, published_config_json, config_version, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (screen_id) DO UPDATE SET
                name = excluded.name,
                online = excluded.online,
                last_seen_at = excluded.last_seen_at,
                secret_hash = excluded.secret_hash,
                source = excluded.source,
                config_json = excluded.config_json,
                published_config_json = excluded.published_config_json,
                config_version = excluded.config_version,
                updated_at = excluded.updated_at
            """,
            (
                screen.screen_id,
                screen.name,
                int(screen.online),
                _epoch(screen.last_seen_at),
                _epoch(screen.created_at),
                screen.secret_hash,
                screen.source,
                json.dumps(screen.config, ensure_ascii=False),
                json.dumps(screen.published_config, ensure_ascii=False),
                screen.config_version,
                _epoch(screen.updated_at),
            ),
        )

    def delete(self, screen_id: str) -> None:
        self._conn.execute("DELETE FROM collab_screens WHERE screen_id = ?", (screen_id,))

    @staticmethod
    def _map(row: Row) -> Screen:
        keys = row.keys()
        return Screen(
            screen_id=row["screen_id"],
            name=row["name"],
            source=row["source"] if "source" in keys else "auto",
            online=bool(row["online"]),
            last_seen_at=_dt(row["last_seen_at"]),
            created_at=_dt(row["created_at"]) or datetime.now(timezone.utc),
            config=_json(row["config_json"]) if "config_json" in keys else {},
            published_config=(
                _json(row["published_config_json"])
                if "published_config_json" in keys else {}
            ),
            config_version=(
                int(row["config_version"])
                if "config_version" in keys and row["config_version"] is not None else 1
            ),
            updated_at=_dt(row["updated_at"]) if "updated_at" in keys else None,
            secret_hash=row["secret_hash"] if "secret_hash" in keys else None,
        )


class SqlitePairRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def list_pairs(
        self,
        *,
        state: str | None = None,
        viewer_id: str | None = None,
        limit: int = 100,
    ) -> list[Pair]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if viewer_id is not None:
            clauses.append("(initiator_id = ? OR partner_id = ?)")
            params.extend([viewer_id, viewer_id])
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM collab_pairs WHERE {' AND '.join(clauses)}"
            " ORDER BY created_at DESC, pair_id DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._map(row) for row in rows]

    def find_active_between(self, left_id: str, right_id: str) -> Pair | None:
        row = self._conn.execute(
            "SELECT * FROM collab_pairs WHERE state = 'active' AND ("
            "(initiator_id = ? AND partner_id = ?) OR"
            "(initiator_id = ? AND partner_id = ?)) LIMIT 1",
            (left_id, right_id, right_id, left_id),
        ).fetchone()
        return None if row is None else self._map(row)

    def get(self, pair_id: str) -> Pair | None:
        row = self._conn.execute(
            "SELECT * FROM collab_pairs WHERE pair_id = ?", (pair_id,)
        ).fetchone()
        return None if row is None else self._map(row)

    def save(self, pair: Pair) -> None:
        self._conn.execute(
            """
            INSERT INTO collab_pairs
                (pair_id, initiator_id, partner_id, state, created_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (pair_id) DO UPDATE SET
                state = excluded.state,
                ended_at = excluded.ended_at
            """,
            (
                pair.pair_id,
                pair.initiator_id,
                pair.partner_id,
                pair.state,
                _epoch(pair.created_at),
                _epoch(pair.ended_at),
            ),
        )

    @staticmethod
    def _map(row: Row) -> Pair:
        return Pair(
            pair_id=row["pair_id"],
            initiator_id=row["initiator_id"],
            partner_id=row["partner_id"],
            state=row["state"],
            created_at=_dt(row["created_at"]) or datetime.now(timezone.utc),
            ended_at=_dt(row["ended_at"]),
        )
