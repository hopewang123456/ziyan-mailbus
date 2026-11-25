"""指标报表的 SQLite 聚合：任务/工作流/Agent 三个视角，同一 owner 过滤。"""

from __future__ import annotations

import sqlite3


def _owners(owners: tuple[str, ...] | None, column: str) -> tuple[str, list]:
    if owners is None:
        return "", []
    if not owners:
        return " AND 1 = 0", []
    marks = ", ".join("?" for _ in owners)
    return f" AND {column} IN ({marks})", list(owners)


class SqliteMetricReportRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def task_summary(self, start: float, end: float, owners) -> dict:
        scope, params = _owners(owners, "owner_id")
        row = self._conn.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN state = 'queued' THEN 1 ELSE 0 END) AS queued,"
            " SUM(CASE WHEN state IN ('queued','running','blocked') THEN 1 ELSE 0 END) AS active,"
            " SUM(CASE WHEN state = 'done' THEN 1 ELSE 0 END) AS done,"
            " SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) AS failed,"
            " SUM(CASE WHEN state = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,"
            " AVG(CASE WHEN state = 'done' THEN updated_at - created_at END) AS avg_done"
            " FROM task_tasks WHERE created_at BETWEEN ? AND ?" + scope,
            (start, end, *params),
        ).fetchone()
        escalations = self._conn.execute(
            "SELECT COUNT(*) AS total FROM task_escalations e"
            " JOIN task_tasks t ON t.task_id = e.task_id"
            " WHERE t.created_at BETWEEN ? AND ?" + _owners(owners, "t.owner_id")[0],
            (start, end, *_owners(owners, "t.owner_id")[1]),
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "queued": int(row["queued"] or 0),
            "active": int(row["active"] or 0),
            "done": int(row["done"] or 0),
            "failed": int(row["failed"] or 0),
            "cancelled": int(row["cancelled"] or 0),
            "avg_done_minutes": round((row["avg_done"] or 0.0) / 60.0, 1),
            "escalations": int(escalations["total"] or 0),
        }

    def task_timeline(self, start: float, end: float, owners):
        scope, params = _owners(owners, "owner_id")
        rows = self._conn.execute(
            "SELECT created_at, updated_at, state FROM task_tasks"
            " WHERE (created_at BETWEEN ? AND ?"
            " OR (state = 'done' AND updated_at BETWEEN ? AND ?))" + scope,
            (start, end, start, end, *params),
        ).fetchall()
        return [(row["created_at"], row["updated_at"], row["state"]) for row in rows]

    def workflow_breakdown(self, start: float, end: float, owners):
        scope, params = _owners(owners, "t.owner_id")
        rows = self._conn.execute(
            "SELECT t.workflow_id, COALESCE(d.name, '') AS name, COUNT(*) AS total,"
            " SUM(CASE WHEN t.state = 'done' THEN 1 ELSE 0 END) AS done,"
            " SUM(CASE WHEN t.state = 'failed' THEN 1 ELSE 0 END) AS failed,"
            " AVG(CASE WHEN t.state = 'done' THEN t.updated_at - t.created_at END) AS avg_done"
            " FROM task_tasks t LEFT JOIN wf_defs d ON d.workflow_id = t.workflow_id"
            " WHERE t.created_at BETWEEN ? AND ? AND t.workflow_id IS NOT NULL" + scope
            + " GROUP BY t.workflow_id",
            (start, end, *params),
        ).fetchall()
        return [
            (
                row["workflow_id"], row["name"], int(row["total"]),
                int(row["done"] or 0), int(row["failed"] or 0),
                float(row["avg_done"] or 0.0),
            )
            for row in rows
        ]

    def agent_breakdown(self, start: float, end: float, owners):
        scope, params = _owners(owners, "r.assigned_employee_id")
        rows = self._conn.execute(
            "SELECT r.assigned_employee_id AS employee_id,"
            " COALESCE(e.display_name, '') AS name, COUNT(*) AS total,"
            " SUM(CASE WHEN r.state = 'failed' THEN 1 ELSE 0 END) AS failed,"
            " SUM(CASE WHEN r.state IN ('dispatched','running','blocked') THEN 1 ELSE 0 END)"
            " AS active FROM task_node_runs r"
            " LEFT JOIN identity_employees e ON e.employee_id = r.assigned_employee_id"
            " WHERE r.assigned_employee_id IS NOT NULL"
            " AND COALESCE(r.started_at, r.dispatched_at, 0) BETWEEN ? AND ?" + scope
            + " GROUP BY r.assigned_employee_id",
            (start, end, *params),
        ).fetchall()
        return [
            (
                row["employee_id"], row["name"], int(row["total"]),
                int(row["failed"] or 0), int(row["active"] or 0),
            )
            for row in rows
        ]

    def online_agents(self, cutoff: float) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM agents WHERE enabled = 1"
            " AND deleted_at IS NULL AND last_seen_at >= ?",
            (cutoff,),
        ).fetchone()
        return int(row["total"] or 0)
