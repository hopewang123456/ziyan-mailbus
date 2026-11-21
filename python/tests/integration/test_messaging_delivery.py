"""B5 集成：投递尝试、总览/日志投影与 SSE 快照（不启动后台循环）。"""

from __future__ import annotations

from contextlib import closing
from datetime import timedelta

from mailbus.adapters.persistence.sqlite.connection import connect
from mailbus.adapters.persistence.sqlite.maintenance import (
    SqliteMaintenance,
    cutoff_from,
)
from mailbus.adapters.persistence.sqlite.migrations import apply_migrations
from mailbus.adapters.persistence.sqlite.uow import SqliteUnitOfWork
from mailbus.adapters.system.clock import SystemClock
from mailbus.adapters.system.ids import UuidGenerator
from mailbus.adapters.transport.null import NullTransport
from mailbus.api import sse
from mailbus.application.dispatch.dispatcher import Dispatcher
from mailbus.application.identity.dto import Actor
from mailbus.application.messaging.dto import make_send_command
from mailbus.application.messaging.service import MessagingService
from mailbus.bootstrap.container import Container
from mailbus.bootstrap.settings import Settings
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.values import Capability, DataScope


def _actor() -> Actor:
    return Actor(
        employee_id="emp-test",
        account_type=AccountType.HUMAN,
        status=EmployeeStatus.ACTIVE,
        capabilities=frozenset({Capability.ALL}),
        data_scope=DataScope.GLOBAL,
    )


def _migrated(tmp_path):
    db_path = tmp_path / "mailbus.db"
    with closing(connect(db_path)) as conn:
        apply_migrations(conn)
    return db_path


def test_dispatcher_records_one_delivery_attempt_per_message(tmp_path):
    db_path = _migrated(tmp_path)
    clock = SystemClock()
    ids = UuidGenerator()
    uow = lambda: SqliteUnitOfWork(lambda: connect(db_path), clock)
    messages = MessagingService(uow, clock, ids)

    message = messages.send(
        _actor(), make_send_command("你好", recipient_id="emp-recipient")
    )
    assert messages.attempts(_actor(), message.message_id) == ()

    dispatcher = Dispatcher(uow, NullTransport(), on_result=messages.record_delivery)
    dispatcher.tick()
    dispatcher.tick()

    attempts = messages.attempts(_actor(), message.message_id)
    assert len(attempts) == 1
    assert attempts[0].ok is True


def test_overview_log_and_sse_snapshot_are_read_projections(tmp_path):
    container = Container(Settings(data_dir=tmp_path))
    with closing(connect(container.settings.db_path)) as conn:
        apply_migrations(conn)

    container.messages.send(_actor(), make_send_command("播报一下"))

    overview = container.overview.get()
    assert overview.messages_total == 1
    assert overview.tasks_total == 0
    assert overview.approvals_pending == 0

    entries = container.log.recent(_actor(), 10)
    assert entries and entries[0].kind == "message.sent"
    assert entries[0].created_at is not None

    payload = sse._encode(sse.snapshot(container, _actor()))
    assert '"overview"' in payload
    assert '"message.sent"' in payload


def test_maintenance_prunes_old_support_rows(tmp_path):
    """M6：过期支撑数据被清理，未派发事件与有效会话保留。"""
    db_path = _migrated(tmp_path)
    clock = SystemClock()
    now = clock.now()
    old = (now - timedelta(days=30)).timestamp()
    with closing(connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO identity_employees (employee_id, display_name, account_type,"
            " status, created_at, updated_at) VALUES ('emp1', '甲', 'human', 'active', ?, ?)",
            (old, old),
        )
        conn.execute(
            "INSERT INTO ops_outbox (event_id, kind, payload, attempts, due_at,"
            " created_at, dispatched_at) VALUES ('done', 'message.sent', '{}', 0, ?, ?, ?)",
            (old, old, old),
        )
        conn.execute(
            "INSERT INTO ops_outbox (event_id, kind, payload, attempts, due_at, created_at)"
            " VALUES ('pending', 'message.sent', '{}', 0, ?, ?)",
            (old, old),
        )
        conn.execute(
            "INSERT INTO ops_audit_log (action, created_at) VALUES ('a', ?)", (old,)
        )
        conn.execute(
            "INSERT INTO ops_idempotency_keys (scope, key, payload_hash, response,"
            " created_at) VALUES ('s', 'k', 'h', '{}', ?)",
            (old,),
        )
        conn.execute(
            "INSERT INTO identity_sessions (token_hash, employee_id, issued_at, expires_at)"
            " VALUES ('h1', 'emp1', ?, ?)",
            (old, old),
        )
        conn.execute(
            "INSERT INTO identity_sessions (token_hash, employee_id, issued_at, expires_at)"
            " VALUES ('h2', 'emp1', ?, NULL)",
            (old,),
        )
        conn.execute(
            "INSERT INTO collab_screens (screen_id, name, online, last_seen_at, created_at)"
            " VALUES ('old-screen', '旧屏', 1, ?, ?)",
            (old, old),
        )
        conn.execute(
            "INSERT INTO collab_screens (screen_id, name, online, last_seen_at, created_at)"
            " VALUES ('fresh-screen', '新屏', 1, ?, ?)",
            (now.timestamp(), now.timestamp()),
        )

        removed = SqliteMaintenance(conn).prune(cutoff_from(now, 7))

        assert removed == 5
        assert conn.execute("SELECT COUNT(*) FROM ops_outbox").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ops_audit_log").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM ops_idempotency_keys").fetchone()[0] == 0
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM identity_sessions").fetchone()[0] == 1
        )
        assert [
            row[0] for row in conn.execute("SELECT screen_id FROM collab_screens")
        ] == ["fresh-screen"]
