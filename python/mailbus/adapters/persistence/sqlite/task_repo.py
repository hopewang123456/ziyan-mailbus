"""任务执行实例、产物、升级与变量的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone

from mailbus.core.workflow.models import (
    TaskArtifact,
    TaskEscalation,
    TaskRun,
    TaskVariable,
)
from mailbus.core.workflow.values import RunState


def _to_epoch(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


class SqliteTaskRunRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, run: TaskRun) -> None:
        self._conn.execute(
            "INSERT INTO task_node_runs (run_id, task_id, node_id, attempt_no,"
            " fanout_slot, assigned_employee_id, role_id, state, fanout_group,"
            " short_fanout, result, parent_run_id, dispatched_at, started_at,"
            " completed_at, deadline_at, escalated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.run_id,
                run.task_id,
                run.node_id,
                run.attempt_no,
                run.fanout_slot,
                run.assigned_employee_id,
                run.role_id,
                run.state.value,
                run.fanout_group,
                1 if run.short_fanout else 0,
                run.result,
                run.parent_run_id,
                _to_epoch(run.dispatched_at),
                _to_epoch(run.started_at),
                _to_epoch(run.completed_at),
                _to_epoch(run.deadline_at),
                _to_epoch(run.escalated_at),
            ),
        )

    def save(self, run: TaskRun) -> None:
        self._conn.execute(
            "UPDATE task_node_runs SET assigned_employee_id = ?, role_id = ?,"
            " state = ?, result = ?, dispatched_at = ?, started_at = ?,"
            " completed_at = ?, deadline_at = ?, escalated_at = ? WHERE run_id = ?",
            (
                run.assigned_employee_id,
                run.role_id,
                run.state.value,
                run.result,
                _to_epoch(run.dispatched_at),
                _to_epoch(run.started_at),
                _to_epoch(run.completed_at),
                _to_epoch(run.deadline_at),
                _to_epoch(run.escalated_at),
                run.run_id,
            ),
        )

    def get(self, run_id: str) -> TaskRun | None:
        row = self._conn.execute(
            "SELECT * FROM task_node_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return None if row is None else _run_from_row(row)

    def list_by_task(self, task_id: str) -> list[TaskRun]:
        rows = self._conn.execute(
            "SELECT * FROM task_node_runs WHERE task_id = ?"
            " ORDER BY node_id, fanout_slot, attempt_no",
            (task_id,),
        ).fetchall()
        return [_run_from_row(row) for row in rows]

    def list_by_node(self, task_id: str, node_id: str) -> list[TaskRun]:
        rows = self._conn.execute(
            "SELECT * FROM task_node_runs WHERE task_id = ? AND node_id = ?"
            " ORDER BY fanout_slot, attempt_no",
            (task_id, node_id),
        ).fetchall()
        return [_run_from_row(row) for row in rows]

    def latest(self, task_id: str, node_id: str, fanout_slot: int = 0) -> TaskRun | None:
        row = self._conn.execute(
            "SELECT * FROM task_node_runs WHERE task_id = ? AND node_id = ?"
            " AND fanout_slot = ? ORDER BY attempt_no DESC LIMIT 1",
            (task_id, node_id, fanout_slot),
        ).fetchone()
        return None if row is None else _run_from_row(row)

    def max_attempt(self, task_id: str, node_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(attempt_no) AS n FROM task_node_runs"
            " WHERE task_id = ? AND node_id = ?",
            (task_id, node_id),
        ).fetchone()
        return int(row["n"] or 0)

    def claim(self, run_id: str, employee_id: str, started_at: datetime) -> bool:
        cursor = self._conn.execute(
            "UPDATE task_node_runs SET assigned_employee_id = ?, state = ?,"
            " started_at = ? WHERE run_id = ? AND state = ?"
            " AND assigned_employee_id IS NULL",
            (
                employee_id,
                RunState.RUNNING.value,
                _to_epoch(started_at),
                run_id,
                RunState.WAITING_HUMAN.value,
            ),
        )
        return cursor.rowcount == 1

    def count_active_by_employee(self, employee_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM task_node_runs WHERE assigned_employee_id = ?"
            " AND state IN ('dispatched', 'running', 'waiting_human')",
            (employee_id,),
        ).fetchone()
        return int(row["n"])

    def list_overdue(self, now: datetime, limit: int = 100) -> list[TaskRun]:
        rows = self._conn.execute(
            "SELECT * FROM task_node_runs WHERE deadline_at IS NOT NULL"
            " AND deadline_at <= ? AND state IN"
            " ('pending', 'dispatched', 'running', 'waiting_human')"
            " ORDER BY deadline_at LIMIT ?",
            (now.timestamp(), limit),
        ).fetchall()
        return [_run_from_row(row) for row in rows]


class SqliteTaskArtifactRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, artifact: TaskArtifact) -> None:
        self._conn.execute(
            "INSERT INTO task_node_artifacts (artifact_id, task_id, node_id, run_id,"
            " file_path, file_name, artifact_type, description, created_by,"
            " created_at, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                artifact.artifact_id,
                artifact.task_id,
                artifact.node_id,
                artifact.run_id,
                artifact.file_path,
                artifact.file_name,
                artifact.artifact_type,
                artifact.description,
                artifact.created_by,
                _to_epoch(artifact.created_at or self._clock.now()),
                artifact.version,
            ),
        )

    def get(self, artifact_id: str) -> TaskArtifact | None:
        row = self._conn.execute(
            "SELECT * FROM task_node_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        return None if row is None else _artifact_from_row(row)

    def list_by_task(self, task_id: str) -> list[TaskArtifact]:
        rows = self._conn.execute(
            "SELECT * FROM task_node_artifacts WHERE task_id = ?"
            " ORDER BY created_at, artifact_id",
            (task_id,),
        ).fetchall()
        return [_artifact_from_row(row) for row in rows]

    def delete_for_node_except(
        self, task_id: str, node_id: str, keep_run_id: str
    ) -> None:
        self._conn.execute(
            "DELETE FROM task_node_artifacts WHERE task_id = ? AND node_id = ?"
            " AND run_id <> ?",
            (task_id, node_id, keep_run_id),
        )


class SqliteTaskEscalationRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, escalation: TaskEscalation) -> None:
        self._conn.execute(
            "INSERT INTO task_escalations (escalation_id, task_id, run_id,"
            " approval_id, reason, escalated_to, escalated_at, level, resolved_by,"
            " resolved_at, resolution) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                escalation.escalation_id,
                escalation.task_id,
                escalation.run_id,
                escalation.approval_id,
                escalation.reason,
                escalation.escalated_to,
                _to_epoch(escalation.escalated_at or self._clock.now()),
                escalation.level,
                escalation.resolved_by,
                _to_epoch(escalation.resolved_at),
                escalation.resolution,
            ),
        )

    def list_by_task(self, task_id: str) -> list[TaskEscalation]:
        rows = self._conn.execute(
            "SELECT * FROM task_escalations WHERE task_id = ?"
            " ORDER BY escalated_at, escalation_id",
            (task_id,),
        ).fetchall()
        return [_escalation_from_row(row) for row in rows]

    def has_open(self, task_id: str, reason: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM task_escalations WHERE task_id = ? AND reason = ?"
            " AND resolved_at IS NULL LIMIT 1",
            (task_id, reason),
        ).fetchone()
        return row is not None


class SqliteTaskVariableRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add_many(self, variables: Sequence[TaskVariable]) -> None:
        for variable in variables:
            self.upsert(variable)

    def upsert(self, variable: TaskVariable) -> None:
        self._conn.execute(
            "INSERT INTO task_variables (task_id, var_key, var_value, source,"
            " updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (task_id, var_key) DO UPDATE SET"
            " var_value = excluded.var_value, updated_by = excluded.updated_by,"
            " updated_at = excluded.updated_at",
            (
                variable.task_id,
                variable.key,
                variable.value,
                variable.source,
                variable.updated_by,
                _to_epoch(variable.updated_at or self._clock.now()),
            ),
        )

    def list_by_task(self, task_id: str) -> list[TaskVariable]:
        rows = self._conn.execute(
            "SELECT * FROM task_variables WHERE task_id = ? ORDER BY var_key",
            (task_id,),
        ).fetchall()
        return [_variable_from_row(row) for row in rows]


def _run_from_row(row: sqlite3.Row) -> TaskRun:
    return TaskRun(
        run_id=row["run_id"],
        task_id=row["task_id"],
        node_id=row["node_id"],
        attempt_no=int(row["attempt_no"]),
        state=RunState(row["state"]),
        fanout_slot=int(row["fanout_slot"]),
        assigned_employee_id=row["assigned_employee_id"],
        role_id=row["role_id"],
        fanout_group=row["fanout_group"],
        short_fanout=bool(row["short_fanout"]),
        result=row["result"],
        parent_run_id=row["parent_run_id"],
        dispatched_at=_from_epoch(row["dispatched_at"]),
        started_at=_from_epoch(row["started_at"]),
        completed_at=_from_epoch(row["completed_at"]),
        deadline_at=_from_epoch(row["deadline_at"]),
        escalated_at=_from_epoch(row["escalated_at"]),
    )


def _artifact_from_row(row: sqlite3.Row) -> TaskArtifact:
    return TaskArtifact(
        artifact_id=row["artifact_id"],
        task_id=row["task_id"],
        node_id=row["node_id"],
        run_id=row["run_id"],
        file_path=row["file_path"],
        file_name=row["file_name"],
        artifact_type=row["artifact_type"],
        description=row["description"],
        created_by=row["created_by"],
        created_at=_from_epoch(row["created_at"]),
        version=int(row["version"]),
    )


def _escalation_from_row(row: sqlite3.Row) -> TaskEscalation:
    return TaskEscalation(
        escalation_id=row["escalation_id"],
        task_id=row["task_id"],
        run_id=row["run_id"],
        approval_id=row["approval_id"],
        reason=row["reason"],
        escalated_to=row["escalated_to"],
        escalated_at=_from_epoch(row["escalated_at"]),
        level=int(row["level"]),
        resolved_by=row["resolved_by"],
        resolved_at=_from_epoch(row["resolved_at"]),
        resolution=row["resolution"],
    )


def _variable_from_row(row: sqlite3.Row) -> TaskVariable:
    return TaskVariable(
        task_id=row["task_id"],
        key=row["var_key"],
        value=row["var_value"],
        source=row["source"],
        updated_by=row["updated_by"],
        updated_at=_from_epoch(row["updated_at"]),
    )
