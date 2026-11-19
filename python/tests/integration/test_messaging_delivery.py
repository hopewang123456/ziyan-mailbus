"""B5 集成：投递尝试、总览/日志投影与 SSE 快照（不启动后台循环）。"""

from __future__ import annotations

from contextlib import closing

from mailbus.adapters.persistence.sqlite.connection import connect
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

    entries = container.log.recent(10)
    assert entries and entries[0].kind == "message.sent"
    assert entries[0].created_at is not None

    payload = sse._encode(sse.snapshot(container))
    assert '"overview"' in payload
    assert '"message.sent"' in payload
