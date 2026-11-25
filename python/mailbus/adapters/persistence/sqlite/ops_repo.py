"""运维域 SQLite 仓储：审计查询、告警与通知规则、评估聚合。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from mailbus.core.ops.models import Alert, AlertRule, AuditEntry


def _dt(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _epoch(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp()


def _audit(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        audit_id=row["audit_id"],
        actor_id=row["actor_id"],
        action=row["action"],
        resource=row["resource"],
        detail=json.loads(row["detail"] or "{}"),
        created_at=_dt(row["created_at"]),
    )


def _rule(row: sqlite3.Row) -> AlertRule:
    return AlertRule(
        rule_id=row["rule_id"],
        name=row["name"],
        alert_type=row["alert_type"],
        threshold=row["threshold"],
        channel=row["channel"],
        target=row["target"],
        silence_seconds=row["silence_seconds"],
        enabled=bool(row["enabled"]),
        created_by=row["created_by"],
        created_at=_dt(row["created_at"]),
    )


def _alert(row: sqlite3.Row) -> Alert:
    return Alert(
        alert_id=row["alert_id"],
        rule_id=row["rule_id"],
        type=row["type"],
        severity=row["severity"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        status=row["status"],
        value=row["value"],
        threshold=row["threshold"],
        first_seen_at=_dt(row["first_seen_at"]),
        last_seen_at=_dt(row["last_seen_at"]),
        acked_by=row["acked_by"],
        acked_at=_dt(row["acked_at"]),
        resolved_at=_dt(row["resolved_at"]),
    )


def _filters(actor, action, resource, start, end) -> tuple[str, list]:
    clauses, params = [], []
    if actor:
        clauses.append("actor_id = ?")
        params.append(actor)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if resource:
        clauses.append("resource = ?")
        params.append(resource)
    if start is not None:
        clauses.append("created_at >= ?")
        params.append(start)
    if end is not None:
        clauses.append("created_at <= ?")
        params.append(end)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


class SqliteOpsRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    # ---- 审计 ----

    def list_audit(self, actor, action, resource, start, end, limit, offset):
        where, params = _filters(actor, action, resource, start, end)
        rows = self._conn.execute(
            "SELECT * FROM ops_audit_log" + where
            + " ORDER BY created_at DESC, audit_id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [_audit(row) for row in rows]

    def count_audit(self, actor, action, resource, start, end) -> int:
        where, params = _filters(actor, action, resource, start, end)
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM ops_audit_log" + where, params
        ).fetchone()
        return int(row["total"])

    def get_audit(self, audit_id: int) -> AuditEntry | None:
        row = self._conn.execute(
            "SELECT * FROM ops_audit_log WHERE audit_id = ?", (audit_id,)
        ).fetchone()
        return None if row is None else _audit(row)

    # ---- 通知规则 ----

    def list_rules(self, limit: int, offset: int) -> list[AlertRule]:
        rows = self._conn.execute(
            "SELECT * FROM ops_alert_rules ORDER BY created_at DESC, rule_id"
            " LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_rule(row) for row in rows]

    def count_rules(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM ops_alert_rules").fetchone()[0])

    def list_enabled_rules(self) -> list[AlertRule]:
        rows = self._conn.execute(
            "SELECT * FROM ops_alert_rules WHERE enabled = 1 ORDER BY rule_id"
        ).fetchall()
        return [_rule(row) for row in rows]

    def get_rule(self, rule_id: str) -> AlertRule | None:
        row = self._conn.execute(
            "SELECT * FROM ops_alert_rules WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        return None if row is None else _rule(row)

    def save_rule(self, rule: AlertRule) -> None:
        self._conn.execute(
            "INSERT INTO ops_alert_rules (rule_id, name, alert_type, threshold, channel,"
            " target, silence_seconds, enabled, created_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (rule_id) DO UPDATE SET name = excluded.name,"
            " alert_type = excluded.alert_type, threshold = excluded.threshold,"
            " channel = excluded.channel, target = excluded.target,"
            " silence_seconds = excluded.silence_seconds, enabled = excluded.enabled",
            (
                rule.rule_id, rule.name, rule.alert_type, rule.threshold, rule.channel,
                rule.target, rule.silence_seconds, int(rule.enabled), rule.created_by,
                _epoch(rule.created_at),
            ),
        )

    def delete_rule(self, rule_id: str) -> None:
        self._conn.execute("DELETE FROM ops_alert_rules WHERE rule_id = ?", (rule_id,))

    # ---- 告警 ----

    def list_alerts(self, state, severity, limit, offset) -> list[Alert]:
        where, params = _alert_filters(state, severity)
        rows = self._conn.execute(
            "SELECT * FROM ops_alerts" + where
            + " ORDER BY last_seen_at DESC, alert_id LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [_alert(row) for row in rows]

    def count_alerts(self, state, severity) -> int:
        where, params = _alert_filters(state, severity)
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM ops_alerts" + where, params
        ).fetchone()
        return int(row["total"])

    def get_alert(self, alert_id: str) -> Alert | None:
        row = self._conn.execute(
            "SELECT * FROM ops_alerts WHERE alert_id = ?", (alert_id,)
        ).fetchone()
        return None if row is None else _alert(row)

    def save_alert(self, alert: Alert) -> None:
        self._conn.execute(
            "INSERT INTO ops_alerts (alert_id, rule_id, type, severity, resource_type,"
            " resource_id, status, value, threshold, first_seen_at, last_seen_at,"
            " acked_by, acked_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (alert_id) DO UPDATE SET status = excluded.status,"
            " value = excluded.value, threshold = excluded.threshold,"
            " last_seen_at = excluded.last_seen_at, acked_by = excluded.acked_by,"
            " acked_at = excluded.acked_at, resolved_at = excluded.resolved_at",
            (
                alert.alert_id, alert.rule_id, alert.type, alert.severity,
                alert.resource_type, alert.resource_id, alert.status, alert.value,
                alert.threshold, _epoch(alert.first_seen_at), _epoch(alert.last_seen_at),
                alert.acked_by, _epoch(alert.acked_at), _epoch(alert.resolved_at),
            ),
        )

    def active_alerts(self, rule_id: str) -> list[Alert]:
        rows = self._conn.execute(
            "SELECT * FROM ops_alerts WHERE rule_id = ? AND status != 'resolved'",
            (rule_id,),
        ).fetchall()
        return [_alert(row) for row in rows]

    # ---- 通知冷却与评估数据 ----

    def last_notification(self, resource: str) -> datetime | None:
        row = self._conn.execute(
            "SELECT MAX(created_at) AS latest FROM ops_audit_log"
            " WHERE action = 'alert.notified' AND resource = ?",
            (resource,),
        ).fetchone()
        return _dt(row["latest"])

    def offline_agents(self, cutoff: float) -> list[tuple[str, str, float]]:
        rows = self._conn.execute(
            "SELECT agent_id, name, last_seen_at FROM agents"
            " WHERE enabled = 1 AND deleted_at IS NULL"
            " AND last_seen_at IS NOT NULL AND last_seen_at < ?"
            " ORDER BY agent_id",
            (cutoff,),
        ).fetchall()
        return [(row["agent_id"], row["name"], row["last_seen_at"]) for row in rows]

    def timed_out_runs(self, cutoff: float) -> list[tuple[str, str, float]]:
        rows = self._conn.execute(
            "SELECT run_id, task_id, started_at FROM task_node_runs"
            " WHERE state = 'running' AND started_at IS NOT NULL AND started_at < ?"
            " ORDER BY run_id",
            (cutoff,),
        ).fetchall()
        return [(row["run_id"], row["task_id"], row["started_at"]) for row in rows]

    def stale_escalations(self, cutoff: float) -> list[tuple[str, str, float]]:
        rows = self._conn.execute(
            "SELECT e.escalation_id, e.task_id, r.started_at AS since FROM task_escalations e"
            " JOIN task_node_runs r ON r.run_id = e.run_id"
            " WHERE r.state = 'blocked' AND r.started_at IS NOT NULL AND r.started_at < ?"
            " ORDER BY e.escalation_id",
            (cutoff,),
        ).fetchall()
        return [(row["escalation_id"], row["task_id"], row["since"]) for row in rows]

    def outbox_backlog(self) -> int:
        return int(self._conn.execute(
            "SELECT COUNT(*) FROM ops_outbox WHERE dispatched_at IS NULL"
        ).fetchone()[0])

    def workflow_failures(self, since: float) -> list[tuple[str, str, int, int]]:
        rows = self._conn.execute(
            "SELECT t.workflow_id, COALESCE(d.name, '') AS name, COUNT(*) AS total,"
            " SUM(CASE WHEN t.state = 'failed' THEN 1 ELSE 0 END) AS failed"
            " FROM task_tasks t LEFT JOIN wf_defs d ON d.workflow_id = t.workflow_id"
            " WHERE t.created_at >= ? AND t.workflow_id IS NOT NULL"
            " GROUP BY t.workflow_id ORDER BY t.workflow_id",
            (since,),
        ).fetchall()
        return [
            (row["workflow_id"], row["name"], int(row["total"]), int(row["failed"] or 0))
            for row in rows
        ]


def _alert_filters(state, severity) -> tuple[str, list]:
    clauses, params = [], []
    if state:
        clauses.append("status = ?")
        params.append(state)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params
