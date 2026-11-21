"""协同上下文的 SQLite 仓储：大屏与结对。"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlite3 import Connection, Row

from mailbus.core.collab.models import Pair, Screen


def _dt(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _epoch(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp()


class SqliteScreenRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[Screen]:
        rows = self._conn.execute(
            "SELECT * FROM collab_screens ORDER BY created_at, screen_id"
        ).fetchall()
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
                (screen_id, name, floor_id, seat_id, online, last_seen_at, created_at, secret)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (screen_id) DO UPDATE SET
                name = excluded.name,
                floor_id = excluded.floor_id,
                seat_id = excluded.seat_id,
                online = excluded.online,
                last_seen_at = excluded.last_seen_at,
                secret = excluded.secret
            """,
            (
                screen.screen_id,
                screen.name,
                screen.floor_id,
                screen.seat_id,
                int(screen.online),
                _epoch(screen.last_seen_at),
                _epoch(screen.created_at),
                screen.secret,
            ),
        )

    @staticmethod
    def _map(row: Row) -> Screen:
        return Screen(
            screen_id=row["screen_id"],
            name=row["name"],
            floor_id=row["floor_id"],
            seat_id=row["seat_id"],
            online=bool(row["online"]),
            last_seen_at=_dt(row["last_seen_at"]),
            created_at=_dt(row["created_at"]) or datetime.now(timezone.utc),
            secret=row["secret"],
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
