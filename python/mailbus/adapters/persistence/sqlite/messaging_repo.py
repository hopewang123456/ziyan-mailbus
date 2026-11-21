"""消息上下文的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from mailbus.core.messaging.models import DeliveryAttempt, Message


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


# 每条消息的最后一次投递结果只聚合一次（LEFT JOIN），不逐行执行相关子查询。
_DELIVERY_STATUS = (
    "COALESCE(CASE WHEN a.ok = 1 THEN 'delivered' ELSE 'failed' END, 'pending')"
)
_LATEST_ATTEMPT_JOIN = (
    " LEFT JOIN ("
    " SELECT x.message_id, x.ok FROM msg_delivery_attempts x"
    " JOIN (SELECT message_id, MAX(attempt_no) AS attempt_no"
    " FROM msg_delivery_attempts GROUP BY message_id) last"
    " ON last.message_id = x.message_id AND last.attempt_no = x.attempt_no"
    ") a ON a.message_id = m.message_id"
)


class SqliteMessageRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, message: Message) -> None:
        self._conn.execute(
            "INSERT INTO msg_messages (message_id, sender_id, recipient_id, kind, body,"
            " created_at, channel, pair_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (message_id) DO NOTHING",
            (
                message.message_id,
                message.sender_id,
                message.recipient_id,
                message.kind,
                message.body,
                _to_epoch(message.created_at or self._clock.now()),
                message.channel,
                message.pair_id,
            ),
        )

    def get(self, message_id: str) -> Message | None:
        row = self._conn.execute(
            "SELECT * FROM msg_messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        return None if row is None else _message_from_row(row)

    def inbox(
        self, recipient_id: str, limit: int | None = None, offset: int = 0
    ) -> list[Message]:
        sql = (
            "SELECT * FROM msg_messages WHERE recipient_id = ? OR recipient_id IS NULL"
            " ORDER BY created_at DESC, message_id DESC"
        )
        params: list[object] = [recipient_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        rows = self._conn.execute(sql, params).fetchall()
        return [_message_from_row(row) for row in rows]

    def list_all(self, limit: int = 200) -> list[Message]:
        rows = self._conn.execute(
            "SELECT * FROM msg_messages ORDER BY created_at DESC, message_id DESC LIMIT ?",
            (limit,),
        )
        return [_message_from_row(row) for row in rows]

    def search(
        self,
        *,
        viewer_id: str | None = None,
        agent: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        pair_id: str | None = None,
        collab_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[Message, str]]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if collab_only:
            clauses.append("m.pair_id IS NOT NULL")
        if pair_id:
            clauses.append("m.pair_id = ?")
            params.append(pair_id)
        if viewer_id is not None:
            clauses.append(
                "(m.sender_id = ? OR m.recipient_id = ? OR m.recipient_id IS NULL)"
            )
            params.extend([viewer_id, viewer_id])
        if agent:
            clauses.append("(m.sender_id = ? OR m.recipient_id = ?)")
            params.extend([agent, agent])
        if since is not None:
            clauses.append("m.created_at >= ?")
            params.append(_to_epoch(since))
        if status:
            clauses.append(f"{_DELIVERY_STATUS} = ?")
            params.append(status)
        params.append(limit)
        params.append(offset)
        rows = self._conn.execute(
            f"SELECT m.*, {_DELIVERY_STATUS} AS delivery_status"
            f" FROM msg_messages m{_LATEST_ATTEMPT_JOIN}"
            f" WHERE {' AND '.join(clauses)}"
            " ORDER BY m.created_at DESC, m.message_id DESC LIMIT ? OFFSET ?",
            params,
        )
        return [(_message_from_row(row), row["delivery_status"]) for row in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS total FROM msg_messages").fetchone()[
            "total"
        ]

    def delete(self, message_id: str) -> None:
        self._conn.execute(
            "DELETE FROM msg_delivery_attempts WHERE message_id = ?", (message_id,)
        )
        self._conn.execute(
            "DELETE FROM msg_messages WHERE message_id = ?", (message_id,)
        )

    def add_attempt(
        self,
        message_id: str,
        *,
        ok: bool,
        error_code: str | None,
        detail: str | None,
        at: datetime,
    ) -> DeliveryAttempt:
        attempt_no = (
            self._conn.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 AS next FROM msg_delivery_attempts"
                " WHERE message_id = ?",
                (message_id,),
            ).fetchone()["next"]
        )
        self._conn.execute(
            "INSERT INTO msg_delivery_attempts (message_id, attempt_no, ok, error_code,"
            " detail, at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                message_id,
                attempt_no,
                1 if ok else 0,
                error_code,
                detail,
                _to_epoch(at),
            ),
        )
        return DeliveryAttempt(
            message_id=message_id,
            attempt_no=attempt_no,
            ok=ok,
            error_code=error_code,
            detail=detail,
            at=at,
        )

    def attempts(self, message_id: str) -> list[DeliveryAttempt]:
        rows = self._conn.execute(
            "SELECT * FROM msg_delivery_attempts WHERE message_id = ? ORDER BY attempt_no",
            (message_id,),
        )
        return [_attempt_from_row(row) for row in rows]


def _message_from_row(row: sqlite3.Row) -> Message:
    return Message(
        message_id=row["message_id"],
        sender_id=row["sender_id"],
        recipient_id=row["recipient_id"],
        kind=row["kind"],
        body=row["body"],
        created_at=_from_epoch(row["created_at"]),
        channel=row["channel"],
        pair_id=row["pair_id"],
    )


def _attempt_from_row(row: sqlite3.Row) -> DeliveryAttempt:
    return DeliveryAttempt(
        message_id=row["message_id"],
        attempt_no=row["attempt_no"],
        ok=bool(row["ok"]),
        error_code=row["error_code"],
        detail=row["detail"],
        at=_from_epoch(row["at"]),
    )
