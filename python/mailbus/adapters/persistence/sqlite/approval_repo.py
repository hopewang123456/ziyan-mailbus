"""审批上下文的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from mailbus.core.approval.models import ApprovalItem
from mailbus.core.approval.values import ApprovalStatus, ApprovalTier


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


class SqliteApprovalRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, item: ApprovalItem) -> None:
        self._conn.execute(
            "INSERT INTO approval_items (approval_id, task_id, node_id, title, tier,"
            " status, requester_id, note, created_at, expires_at, resolved_by,"
            " resolved_at, resolution_note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (approval_id) DO NOTHING",
            _params(item, self._clock.now()),
        )

    def save(self, item: ApprovalItem) -> None:
        self._conn.execute(
            "UPDATE approval_items SET status = ?, resolved_by = ?, resolved_at = ?,"
            " resolution_note = ? WHERE approval_id = ?",
            (
                item.status.value,
                item.resolved_by,
                None if item.resolved_at is None else _to_epoch(item.resolved_at),
                item.resolution_note,
                item.approval_id,
            ),
        )

    def get(self, approval_id: str) -> ApprovalItem | None:
        row = self._conn.execute(
            "SELECT * FROM approval_items WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        return None if row is None else _from_row(row)

    def list_all(
        self, status: ApprovalStatus | None = None, task_id: str | None = None
    ) -> list[ApprovalItem]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM approval_items{where} ORDER BY created_at, approval_id",
            params,
        )
        return [_from_row(row) for row in rows]

    def due_pending(self, now: datetime) -> list[ApprovalItem]:
        rows = self._conn.execute(
            "SELECT * FROM approval_items WHERE status = ? AND expires_at <= ?"
            " ORDER BY expires_at",
            (ApprovalStatus.PENDING.value, _to_epoch(now)),
        )
        return [_from_row(row) for row in rows]


def _params(item: ApprovalItem, now: datetime):
    return (
        item.approval_id,
        item.task_id,
        item.node_id,
        item.title,
        item.tier.value,
        item.status.value,
        item.requester_id,
        item.note,
        _to_epoch(item.created_at or now),
        _to_epoch(item.expires_at or now),
        item.resolved_by,
        None if item.resolved_at is None else _to_epoch(item.resolved_at),
        item.resolution_note,
    )


def _from_row(row: sqlite3.Row) -> ApprovalItem:
    return ApprovalItem(
        approval_id=row["approval_id"],
        task_id=row["task_id"],
        node_id=row["node_id"],
        title=row["title"],
        tier=ApprovalTier(row["tier"]),
        status=ApprovalStatus(row["status"]),
        requester_id=row["requester_id"],
        note=row["note"],
        created_at=_from_epoch(row["created_at"]),
        expires_at=_from_epoch(row["expires_at"]),
        resolved_by=row["resolved_by"],
        resolved_at=_from_epoch(row["resolved_at"]),
        resolution_note=row["resolution_note"],
    )
