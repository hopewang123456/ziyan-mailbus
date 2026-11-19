"""指标治理的 SQLite 仓储：告警规则与大盘布局。"""

from __future__ import annotations

import json
import sqlite3

from mailbus.core.metrics.models import MetricLayout, MetricRule


def _rule_from_row(row: sqlite3.Row) -> MetricRule:
    return MetricRule(
        rule_id=row["rule_id"],
        metric=row["metric"],
        op=row["op"],
        threshold=float(row["threshold"]),
        severity=row["severity"],
        enabled=bool(row["enabled"]),
        note=row["note"],
        actions=tuple(json.loads(row["actions"])),
    )


class SqliteMetricRuleRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def list_all(self) -> list[MetricRule]:
        rows = self._conn.execute(
            "SELECT * FROM metrics_rules ORDER BY rule_id"
        ).fetchall()
        return [_rule_from_row(row) for row in rows]

    def get(self, rule_id: str) -> MetricRule | None:
        row = self._conn.execute(
            "SELECT * FROM metrics_rules WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        return None if row is None else _rule_from_row(row)

    def save(self, rule: MetricRule) -> None:
        self._conn.execute(
            "INSERT INTO metrics_rules (rule_id, metric, op, threshold, severity,"
            " enabled, note, actions) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (rule_id) DO UPDATE SET"
            " metric = excluded.metric, op = excluded.op,"
            " threshold = excluded.threshold, severity = excluded.severity,"
            " enabled = excluded.enabled, note = excluded.note,"
            " actions = excluded.actions",
            (
                rule.rule_id,
                rule.metric,
                rule.op,
                rule.threshold,
                rule.severity,
                int(rule.enabled),
                rule.note,
                json.dumps(list(rule.actions), ensure_ascii=False),
            ),
        )


class SqliteMetricLayoutRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def get(self) -> MetricLayout:
        row = self._conn.execute(
            "SELECT hidden FROM metrics_layout WHERE id = 1"
        ).fetchone()
        if row is None:
            return MetricLayout()
        return MetricLayout(hidden=tuple(json.loads(row["hidden"])))

    def save(self, layout: MetricLayout) -> None:
        self._conn.execute(
            "INSERT INTO metrics_layout (id, hidden) VALUES (1, ?)"
            " ON CONFLICT (id) DO UPDATE SET hidden = excluded.hidden",
            (json.dumps(list(layout.hidden), ensure_ascii=False),),
        )
