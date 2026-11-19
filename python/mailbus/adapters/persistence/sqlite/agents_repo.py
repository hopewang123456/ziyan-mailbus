"""Agent 台账的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from mailbus.core.agents.models import Agent


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _agent_from_row(row: sqlite3.Row) -> Agent:
    return Agent(
        agent_id=row["agent_id"],
        name=row["name"],
        framework=row["framework"],
        model=row["model"],
        endpoint=row["endpoint"],
        enabled=bool(row["enabled"]),
        created_at=_from_epoch(row["created_at"]),
        updated_at=_from_epoch(row["updated_at"]),
    )


class SqliteAgentRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def get(self, agent_id: str) -> Agent | None:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return None if row is None else _agent_from_row(row)

    def save(self, agent: Agent) -> None:
        now = agent.updated_at or self._clock.now()
        created = agent.created_at or now
        self._conn.execute(
            "INSERT INTO agents (agent_id, name, framework, model, endpoint, enabled,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (agent_id) DO UPDATE SET"
            " name = excluded.name,"
            " framework = excluded.framework,"
            " model = excluded.model,"
            " endpoint = excluded.endpoint,"
            " enabled = excluded.enabled,"
            " updated_at = excluded.updated_at",
            (
                agent.agent_id,
                agent.name,
                agent.framework,
                agent.model,
                agent.endpoint,
                int(agent.enabled),
                _to_epoch(created),
                _to_epoch(now),
            ),
        )

    def list_all(self) -> list[Agent]:
        rows = self._conn.execute(
            "SELECT * FROM agents ORDER BY created_at, agent_id"
        ).fetchall()
        return [_agent_from_row(row) for row in rows]
