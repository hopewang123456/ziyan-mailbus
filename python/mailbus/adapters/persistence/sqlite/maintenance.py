"""运行支撑数据的保留期清理。

四张表只增不减会拖慢检索并膨胀数据库：
- ``ops_outbox``：已派发的事件只作为操作日志来源保留一段时间；
- ``ops_audit_log``：审计流水按保留期截断；
- ``ops_idempotency_keys``：幂等键过期后不再需要；
- ``identity_sessions``：已撤销或已过期的会话不再需要。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta


def cutoff_from(now: datetime, retention_days: float) -> datetime:
    """保留期截止时间：早于该时刻的支撑数据可删除。"""
    return now - timedelta(days=retention_days)


class SqliteMaintenance:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def prune(self, older_than: datetime) -> int:
        """删除早于 ``older_than`` 的支撑数据，返回删除总行数。"""
        cutoff = older_than.timestamp()
        removed = 0
        removed += self._delete(
            "DELETE FROM ops_outbox WHERE dispatched_at IS NOT NULL AND dispatched_at < ?",
            (cutoff,),
        )
        removed += self._delete(
            "DELETE FROM ops_audit_log WHERE created_at < ?", (cutoff,)
        )
        removed += self._delete(
            "DELETE FROM ops_idempotency_keys WHERE created_at < ?", (cutoff,)
        )
        removed += self._delete(
            "DELETE FROM identity_sessions"
            " WHERE (revoked_at IS NOT NULL AND revoked_at < ?)"
            " OR (expires_at IS NOT NULL AND expires_at < ?)",
            (cutoff, cutoff),
        )
        return removed

    def _delete(self, sql: str, params: tuple[float, ...]) -> int:
        cursor = self._conn.execute(sql, params)
        return max(cursor.rowcount, 0)
