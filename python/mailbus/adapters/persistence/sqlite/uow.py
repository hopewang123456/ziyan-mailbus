"""SQLite 工作单元与 outbox 仓储。

一个用例 = 一个 UoW = 一个连接；事务边界在 application，不在 api。
连接按 UoW 新建：避免跨线程共享连接，WAL + busy_timeout 负责并发。
派发器单实例运行，claim 不跨进程抢占（多实例部署前需加租约列）。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from mailbus.adapters.persistence.sqlite.agents_repo import SqliteAgentRepository
from mailbus.adapters.persistence.sqlite.approval_repo import SqliteApprovalRepository
from mailbus.adapters.persistence.sqlite.collab_repo import (
    SqlitePairRepository,
    SqliteScreenRepository,
)
from mailbus.adapters.persistence.sqlite.identity_repo import (
    SqliteBootstrapRepository,
    SqliteEmployeeRepository,
    SqliteInviteRepository,
    SqliteSessionRepository,
)
from mailbus.adapters.persistence.sqlite.messaging_repo import SqliteMessageRepository
from mailbus.adapters.persistence.sqlite.metrics_repo import (
    SqliteMetricLayoutRepository,
    SqliteMetricRuleRepository,
)
from mailbus.adapters.persistence.sqlite.metrics_report_repo import (
    SqliteMetricReportRepository,
)
from mailbus.adapters.persistence.sqlite.ops_repo import SqliteOpsRepository
from mailbus.adapters.persistence.sqlite.org_repo import (
    SqlitePositionRepository,
    SqliteRoleRepository,
    SqliteSeatRepository,
    SqliteTeamRepository,
)
from mailbus.adapters.persistence.sqlite.skills_repo import (
    SqliteSkillBindingRepository,
    SqliteSkillPackageRepository,
)
from mailbus.adapters.persistence.sqlite.task_repo import (
    SqliteTaskArtifactRepository,
    SqliteTaskEscalationRepository,
    SqliteTaskRunRepository,
    SqliteTaskVariableRepository,
)
from mailbus.adapters.persistence.sqlite.workflow_graph_repo import (
    SqliteWorkflowGraphRepository,
)
from mailbus.adapters.persistence.sqlite.workflow_repo import (
    SqliteTaskRepository,
    SqliteWorkflowDefinitionRepository,
    SqliteWorkflowVersionRepository,
)
from mailbus.core.shared.events import OutboxEvent
from mailbus.core.shared.ports import Clock

_MAX_BACKOFF_SEC = 60.0


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


class SqliteOutbox:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self._conn = conn
        self._clock = clock

    def enqueue(self, event: OutboxEvent) -> None:
        now = self._clock.now()
        self._conn.execute(
            "INSERT INTO ops_outbox (event_id, kind, payload, attempts, due_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.kind,
                json.dumps(event.payload, ensure_ascii=False),
                event.attempts,
                _to_epoch(event.due_at or now),
                _to_epoch(now),
            ),
        )

    def claim_due(self, limit: int) -> list[OutboxEvent]:
        now = self._clock.now().timestamp()
        rows = self._conn.execute(
            "SELECT event_id, kind, payload, attempts, due_at FROM ops_outbox "
            "WHERE dispatched_at IS NULL AND due_at <= ? ORDER BY due_at LIMIT ?",
            (now, limit),
        ).fetchall()
        return [
            OutboxEvent(
                event_id=row["event_id"],
                kind=row["kind"],
                payload=json.loads(row["payload"]),
                attempts=row["attempts"],
                due_at=_from_epoch(row["due_at"]),
            )
            for row in rows
        ]

    def mark_sent(self, event_id: str) -> None:
        self._conn.execute(
            "UPDATE ops_outbox SET dispatched_at = ?, last_error = NULL WHERE event_id = ?",
            (_to_epoch(self._clock.now()), event_id),
        )

    def mark_failed(self, event_id: str, error_code: str) -> None:
        row = self._conn.execute(
            "SELECT attempts FROM ops_outbox WHERE event_id = ?", (event_id,)
        ).fetchone()
        attempts = (row["attempts"] if row else 0) + 1
        next_due = _to_epoch(self._clock.now()) + min(2.0 ** attempts, _MAX_BACKOFF_SEC)
        self._conn.execute(
            "UPDATE ops_outbox SET attempts = ?, due_at = ?, last_error = ? WHERE event_id = ?",
            (attempts, next_due, error_code, event_id),
        )

    def mark_dead(self, event_id: str, error_code: str) -> None:
        self._conn.execute(
            "UPDATE ops_outbox SET attempts = attempts + 1, dispatched_at = ?,"
            " last_error = ? WHERE event_id = ?",
            (_to_epoch(self._clock.now()), error_code, event_id),
        )

    def recent(self, limit: int) -> list[OutboxEvent]:
        rows = self._conn.execute(
            "SELECT event_id, kind, payload, attempts, due_at, created_at FROM ops_outbox"
            " ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return [
            OutboxEvent(
                event_id=row["event_id"],
                kind=row["kind"],
                payload=json.loads(row["payload"]),
                attempts=row["attempts"],
                due_at=_from_epoch(row["due_at"]),
                created_at=_from_epoch(row["created_at"]),
            )
            for row in rows
        ]


class SqliteAuditLog:
    """审计流水写入；与业务变更同连接、同事务。"""

    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self._conn = conn
        self._clock = clock

    def record(
        self,
        actor_id: str | None,
        action: str,
        resource: str | None,
        detail: dict[str, object],
    ) -> None:
        self._conn.execute(
            "INSERT INTO ops_audit_log (actor_id, action, resource, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                actor_id,
                action,
                resource,
                json.dumps(detail, ensure_ascii=False),
                _to_epoch(self._clock.now()),
            ),
        )


class SqliteUnitOfWork:
    def __init__(self, connect: Callable[[], sqlite3.Connection], clock: Clock) -> None:
        self._connect = connect
        self._clock = clock
        self._conn: sqlite3.Connection | None = None
        self._in_transaction = False
        self._outbox: SqliteOutbox | None = None
        self.employees: SqliteEmployeeRepository
        self.invites: SqliteInviteRepository
        self.sessions: SqliteSessionRepository
        self.teams: SqliteTeamRepository
        self.positions: SqlitePositionRepository
        self.roles: SqliteRoleRepository
        self.seats: SqliteSeatRepository
        self.bootstrap: SqliteBootstrapRepository
        self.definitions: SqliteWorkflowDefinitionRepository
        self.versions: SqliteWorkflowVersionRepository
        self.graphs: SqliteWorkflowGraphRepository
        self.audit: SqliteAuditLog
        self.tasks: SqliteTaskRepository
        self.runs: SqliteTaskRunRepository
        self.artifacts: SqliteTaskArtifactRepository
        self.escalations: SqliteTaskEscalationRepository
        self.variables: SqliteTaskVariableRepository
        self.approvals: SqliteApprovalRepository
        self.messages: SqliteMessageRepository
        self.agents: SqliteAgentRepository
        self.packages: SqliteSkillPackageRepository
        self.bindings: SqliteSkillBindingRepository
        self.metric_rules: SqliteMetricRuleRepository
        self.metric_layout: SqliteMetricLayoutRepository
        self.reports: SqliteMetricReportRepository
        self.ops: SqliteOpsRepository
        self.screens: SqliteScreenRepository
        self.pairs: SqlitePairRepository

    @property
    def outbox(self) -> SqliteOutbox:
        if self._outbox is None:
            raise RuntimeError("UnitOfWork 未进入上下文")
        return self._outbox

    def __enter__(self) -> "SqliteUnitOfWork":
        self._conn = self._connect()
        self._outbox = SqliteOutbox(self._conn, self._clock)
        self.employees = SqliteEmployeeRepository(self._conn, self._clock)
        self.invites = SqliteInviteRepository(self._conn, self._clock)
        self.sessions = SqliteSessionRepository(self._conn, self._clock)
        self.teams = SqliteTeamRepository(self._conn, self._clock)
        self.positions = SqlitePositionRepository(self._conn, self._clock)
        self.roles = SqliteRoleRepository(self._conn, self._clock)
        self.seats = SqliteSeatRepository(self._conn, self._clock)
        self.bootstrap = SqliteBootstrapRepository(self._conn, self._clock)
        self.definitions = SqliteWorkflowDefinitionRepository(self._conn, self._clock)
        self.versions = SqliteWorkflowVersionRepository(self._conn, self._clock)
        self.graphs = SqliteWorkflowGraphRepository(self._conn)
        self.audit = SqliteAuditLog(self._conn, self._clock)
        self.tasks = SqliteTaskRepository(self._conn, self._clock)
        self.runs = SqliteTaskRunRepository(self._conn, self._clock)
        self.artifacts = SqliteTaskArtifactRepository(self._conn, self._clock)
        self.escalations = SqliteTaskEscalationRepository(self._conn, self._clock)
        self.variables = SqliteTaskVariableRepository(self._conn, self._clock)
        self.approvals = SqliteApprovalRepository(self._conn, self._clock)
        self.messages = SqliteMessageRepository(self._conn, self._clock)
        self.agents = SqliteAgentRepository(self._conn, self._clock)
        self.packages = SqliteSkillPackageRepository(self._conn, self._clock)
        self.bindings = SqliteSkillBindingRepository(self._conn, self._clock)
        self.metric_rules = SqliteMetricRuleRepository(self._conn, self._clock)
        self.metric_layout = SqliteMetricLayoutRepository(self._conn, self._clock)
        self.reports = SqliteMetricReportRepository(self._conn, self._clock)
        self.ops = SqliteOpsRepository(self._conn, self._clock)
        self.screens = SqliteScreenRepository(self._conn)
        self.pairs = SqlitePairRepository(self._conn)
        self._conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if self._in_transaction:
                self._conn.execute("ROLLBACK")
                self._in_transaction = False
        finally:
            self._conn.close()
            self._conn = None
        return False

    def commit(self) -> None:
        if self._in_transaction:
            self._conn.execute("COMMIT")
            self._in_transaction = False
