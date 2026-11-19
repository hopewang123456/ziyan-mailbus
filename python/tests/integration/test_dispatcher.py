"""B0 集成：派发器能取件、投递、回写结果与退避。"""

from __future__ import annotations

from mailbus.adapters.persistence.sqlite.connection import connect
from mailbus.adapters.persistence.sqlite.migrations import apply_migrations
from mailbus.adapters.persistence.sqlite.uow import SqliteUnitOfWork
from mailbus.adapters.system.clock import SystemClock
from mailbus.application.dispatch.dispatcher import Dispatcher
from mailbus.core.shared.events import DeliveryResult


class _OkTransport:
    def send(self, event):
        return DeliveryResult(ok=True)


class _FailingTransport:
    def send(self, event):
        return DeliveryResult(ok=False, error_code="boom")


def _seed(db_path) -> None:
    conn = connect(db_path)
    apply_migrations(conn)
    now = SystemClock().now().timestamp()
    conn.execute(
        "INSERT INTO ops_outbox (event_id, kind, payload, attempts, due_at, created_at) "
        "VALUES (?, ?, ?, 0, ?, ?)",
        ("evt_1", "task.completed", "{}", now - 1, now),
    )
    conn.close()


def _dispatcher(db_path, transport) -> Dispatcher:
    clock = SystemClock()
    return Dispatcher(lambda: SqliteUnitOfWork(lambda: connect(db_path), clock), transport)


def _row(db_path):
    conn = connect(db_path)
    row = conn.execute(
        "SELECT attempts, dispatched_at, last_error FROM ops_outbox WHERE event_id = 'evt_1'"
    ).fetchone()
    conn.close()
    return row


def test_tick_marks_event_sent(tmp_path):
    db_path = tmp_path / "mailbus.db"
    _seed(db_path)

    assert _dispatcher(db_path, _OkTransport()).tick() == 1
    assert _row(db_path)["dispatched_at"] is not None


def test_failure_records_attempt_and_backoff(tmp_path):
    db_path = tmp_path / "mailbus.db"
    _seed(db_path)

    assert _dispatcher(db_path, _FailingTransport()).tick() == 1
    row = _row(db_path)
    assert row["attempts"] == 1
    assert row["dispatched_at"] is None
    assert row["last_error"] == "boom"


def test_tick_is_noop_on_empty_outbox(tmp_path):
    db_path = tmp_path / "mailbus.db"
    conn = connect(db_path)
    apply_migrations(conn)
    conn.close()

    assert _dispatcher(db_path, _OkTransport()).tick() == 0
