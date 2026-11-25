"""流程上下文的 SQLite 仓储：定义、版本与任务。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone

from mailbus.core.workflow.models import (
    Task,
    TaskNode,
    WorkflowDef,
    WorkflowNode,
    WorkflowVersion,
)
from mailbus.core.workflow.values import NodeState, TaskState, VersionState


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


class SqliteWorkflowDefinitionRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, definition: WorkflowDef) -> None:
        self._conn.execute(
            "INSERT INTO wf_defs (workflow_id, name, latest_version, published_version,"
            " created_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT (workflow_id) DO NOTHING",
            (
                definition.workflow_id,
                definition.name,
                definition.latest_version,
                definition.published_version,
                _to_epoch(definition.created_at or self._clock.now()),
            ),
        )

    def save(self, definition: WorkflowDef) -> None:
        self._conn.execute(
            "UPDATE wf_defs SET name = ?, latest_version = ?, published_version = ?"
            " WHERE workflow_id = ?",
            (
                definition.name,
                definition.latest_version,
                definition.published_version,
                definition.workflow_id,
            ),
        )

    def get(self, workflow_id: str) -> WorkflowDef | None:
        row = self._conn.execute(
            "SELECT * FROM wf_defs WHERE workflow_id = ?", (workflow_id,)
        ).fetchone()
        return None if row is None else _definition_from_row(row)

    def list_all(
        self, limit: int | None = None, offset: int = 0
    ) -> list[WorkflowDef]:
        sql = (
            "SELECT * FROM wf_defs WHERE deleted_at IS NULL"
            " ORDER BY created_at, workflow_id"
        )
        params: list[object] = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        rows = self._conn.execute(sql, params).fetchall()
        return [_definition_from_row(row) for row in rows]

    def count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM wf_defs WHERE deleted_at IS NULL"
        ).fetchone()
        return int(row["n"])

    def soft_delete(
        self, workflow_id: str, deleted_at: datetime, deleted_by: str | None
    ) -> None:
        self._conn.execute(
            "UPDATE wf_defs SET deleted_at = ?, deleted_by = ?"
            " WHERE workflow_id = ? AND deleted_at IS NULL",
            (_to_epoch(deleted_at), deleted_by, workflow_id),
        )

    def delete(self, workflow_id: str) -> None:
        self._conn.execute(
            "DELETE FROM wf_defs WHERE workflow_id = ?", (workflow_id,)
        )


def _definition_from_row(row: sqlite3.Row) -> WorkflowDef:
    return WorkflowDef(
        workflow_id=row["workflow_id"],
        name=row["name"],
        latest_version=row["latest_version"],
        published_version=row["published_version"],
        created_at=_from_epoch(row["created_at"]),
        deleted_at=_from_epoch(row["deleted_at"]),
    )


class SqliteWorkflowVersionRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, version: WorkflowVersion) -> None:
        self._conn.execute(
            "INSERT INTO wf_versions (workflow_id, version, state, nodes, revision,"
            " created_at, published_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (workflow_id, version) DO NOTHING",
            _version_params(version, self._clock.now()),
        )

    def save(self, version: WorkflowVersion) -> None:
        # 已发布版本不可变：只允许 draft → published 的单向迁移
        if not version.published:
            return
        self._conn.execute(
            "UPDATE wf_versions SET state = ?, published_at = ?"
            " WHERE workflow_id = ? AND version = ? AND state = ?",
            (
                VersionState.PUBLISHED.value,
                _to_epoch(version.published_at or self._clock.now()),
                version.workflow_id,
                version.version,
                VersionState.DRAFT.value,
            ),
        )

    def get(self, workflow_id: str, version: int) -> WorkflowVersion | None:
        row = self._conn.execute(
            "SELECT * FROM wf_versions WHERE workflow_id = ? AND version = ?",
            (workflow_id, version),
        ).fetchone()
        return None if row is None else _version_from_row(row)

    def list_by_workflow(
        self, workflow_id: str, limit: int | None = None, offset: int = 0
    ) -> list[WorkflowVersion]:
        sql = (
            "SELECT * FROM wf_versions WHERE workflow_id = ? ORDER BY version"
        )
        params: list[object] = [workflow_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        rows = self._conn.execute(sql, params).fetchall()
        return [_version_from_row(row) for row in rows]

    def count_by_workflow(self, workflow_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM wf_versions WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return int(row["n"])

    def delete_by_workflow(self, workflow_id: str) -> None:
        self._conn.execute(
            "DELETE FROM wf_versions WHERE workflow_id = ?", (workflow_id,)
        )


def _version_params(version: WorkflowVersion, now: datetime):
    nodes = [
        {"node_id": node.node_id, "name": node.name, "order": node.order}
        for node in version.nodes
    ]
    return (
        version.workflow_id,
        version.version,
        version.state.value,
        json.dumps(nodes, ensure_ascii=False),
        version.revision,
        _to_epoch(version.created_at or now),
        None if version.published_at is None else _to_epoch(version.published_at),
    )


def _version_from_row(row: sqlite3.Row) -> WorkflowVersion:
    nodes = tuple(
        WorkflowNode(node_id=item["node_id"], name=item["name"], order=item["order"])
        for item in json.loads(row["nodes"])
    )
    return WorkflowVersion(
        workflow_id=row["workflow_id"],
        version=row["version"],
        state=VersionState(row["state"]),
        nodes=nodes,
        revision=int(row["revision"]),
        created_at=_from_epoch(row["created_at"]),
        published_at=_from_epoch(row["published_at"]),
    )


class SqliteTaskRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, task: Task, nodes: Sequence[TaskNode]) -> None:
        self._conn.execute(
            "INSERT INTO task_tasks (task_id, title, state, workflow_id, workflow_version,"
            " owner_id, created_by, created_at, updated_at, termination_reason, loop_counters)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (task_id) DO NOTHING",
            (
                task.task_id,
                task.title,
                task.state.value,
                task.workflow_id,
                task.workflow_version,
                task.owner_id,
                task.created_by,
                _to_epoch(task.created_at or self._clock.now()),
                _to_epoch(task.updated_at or self._clock.now()),
                task.termination_reason,
                json.dumps(task.loop_counters, ensure_ascii=False),
            ),
        )
        for node in nodes:
            self._upsert_node(node)

    def save(self, task: Task, nodes: Sequence[TaskNode]) -> None:
        self.save_task(task)
        for node in nodes:
            self._upsert_node(node)

    def save_task(self, task: Task) -> None:
        self._conn.execute(
            "UPDATE task_tasks SET title = ?, state = ?, owner_id = ?,"
            " termination_reason = ?, loop_counters = ?, updated_at = ?"
            " WHERE task_id = ?",
            (
                task.title,
                task.state.value,
                task.owner_id,
                task.termination_reason,
                json.dumps(task.loop_counters, ensure_ascii=False),
                _to_epoch(task.updated_at or self._clock.now()),
                task.task_id,
            ),
        )

    def save_node(self, node: TaskNode) -> None:
        self._upsert_node(node)

    def _upsert_node(self, node: TaskNode) -> None:
        self._conn.execute(
            "INSERT INTO task_nodes (task_id, node_id, name, seq, state,"
            " current_run_id, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (task_id, node_id) DO UPDATE SET"
            " name = excluded.name, seq = excluded.seq,"
            " state = excluded.state, current_run_id = excluded.current_run_id,"
            " updated_at = excluded.updated_at",
            (
                node.task_id,
                node.node_id,
                node.name,
                node.order,
                node.state.value,
                node.current_run_id,
                _to_epoch(node.updated_at or self._clock.now()),
            ),
        )

    def get(self, task_id: str) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM task_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return None if row is None else _task_from_row(row)

    def get_node(self, task_id: str, node_id: str) -> TaskNode | None:
        row = self._conn.execute(
            "SELECT * FROM task_nodes WHERE task_id = ? AND node_id = ?",
            (task_id, node_id),
        ).fetchone()
        return None if row is None else _node_from_row(row)

    def nodes(self, task_id: str) -> list[TaskNode]:
        rows = self._conn.execute(
            "SELECT * FROM task_nodes WHERE task_id = ? ORDER BY seq", (task_id,)
        )
        return [_node_from_row(row) for row in rows]

    def list_all(
        self,
        state: TaskState | None = None,
        owner_id: str | None = None,
        workflow_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        viewer_id: str | None = None,
    ) -> list[Task]:
        clauses, params = _task_filters(state, owner_id, workflow_id, viewer_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM task_tasks{where} ORDER BY created_at, task_id"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        rows = self._conn.execute(sql, params).fetchall()
        return [_task_from_row(row) for row in rows]

    def count(
        self,
        state: TaskState | None = None,
        owner_id: str | None = None,
        workflow_id: str | None = None,
        viewer_id: str | None = None,
    ) -> int:
        clauses, params = _task_filters(state, owner_id, workflow_id, viewer_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM task_tasks{where}", params
        ).fetchone()
        return int(row["n"])

    def soft_delete(
        self, task_id: str, deleted_at: datetime, deleted_by: str | None
    ) -> None:
        self._conn.execute(
            "UPDATE task_tasks SET archived_at = ? WHERE task_id = ?",
            (_to_epoch(deleted_at), task_id),
        )


def _task_filters(
    state: TaskState | None,
    owner_id: str | None,
    workflow_id: str | None,
    viewer_id: str | None,
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if state is not None:
        clauses.append("state = ?")
        params.append(state.value)
    if owner_id is not None:
        clauses.append("owner_id = ?")
        params.append(owner_id)
    if workflow_id is not None:
        clauses.append("workflow_id = ?")
        params.append(workflow_id)
    if viewer_id is not None:
        clauses.append(
            "(owner_id = ? OR created_by = ? OR task_id IN"
            " (SELECT task_id FROM task_node_runs WHERE assigned_employee_id = ?))"
        )
        params.extend((viewer_id, viewer_id, viewer_id))
    return clauses, params


def _task_from_row(row: sqlite3.Row) -> Task:
    state = TaskState(row["state"])
    if state in (TaskState.DRAFT, TaskState.QUEUED):
        state = TaskState.PENDING
    return Task(
        task_id=row["task_id"],
        title=row["title"],
        state=state,
        workflow_id=row["workflow_id"],
        workflow_version=row["workflow_version"],
        owner_id=row["owner_id"],
        created_by=row["created_by"],
        created_at=_from_epoch(row["created_at"]),
        updated_at=_from_epoch(row["updated_at"]),
        termination_reason=row["termination_reason"],
        loop_counters=json.loads(row["loop_counters"] or "{}"),
        archived_at=_from_epoch(row["archived_at"]),
    )


def _node_from_row(row: sqlite3.Row) -> TaskNode:
    return TaskNode(
        task_id=row["task_id"],
        node_id=row["node_id"],
        name=row["name"],
        order=row["seq"],
        state=NodeState(row["state"]),
        current_run_id=row["current_run_id"],
        updated_at=_from_epoch(row["updated_at"]),
    )
