"""B6 集成：通道落盘、A2A 缺失 endpoint 与重试耗尽死信。"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

from mailbus.adapters.persistence.sqlite.connection import connect
from mailbus.adapters.persistence.sqlite.migrations import apply_migrations
from mailbus.adapters.persistence.sqlite.uow import SqliteUnitOfWork
from mailbus.adapters.system.ids import UuidGenerator
from mailbus.adapters.transport.a2a import A2aTransport
from mailbus.adapters.transport.file_bus import FileBusTransport
from mailbus.adapters.transport.mcp_pull import McpPullTransport
from mailbus.adapters.transport.routing import RoutingTransport
from mailbus.application.dispatch.dispatcher import Dispatcher
from mailbus.application.identity.dto import Actor
from mailbus.application.messaging.dto import make_send_command
from mailbus.application.messaging.service import MessagingService
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.events import DeliveryResult, OutboxEvent
from mailbus.core.shared.values import Capability, DataScope


class _FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta) -> None:
        self._now += timedelta(**delta)


class _FailingTransport:
    def send(self, event):
        return DeliveryResult(ok=False, error_code="boom")


def _actor() -> Actor:
    return Actor(
        employee_id="emp-test",
        account_type=AccountType.HUMAN,
        status=EmployeeStatus.ACTIVE,
        capabilities=frozenset({Capability.ALL}),
        data_scope=DataScope.GLOBAL,
    )


def _event(channel: str) -> OutboxEvent:
    return OutboxEvent(
        event_id=f"evt-{channel}",
        kind="message.sent",
        payload={"recipient_id": "emp-1", "channel": channel},
    )


def test_local_channels_stage_and_drain(tmp_path):
    assert FileBusTransport(tmp_path / "fb").send(_event("file_bus")).ok is True
    assert (tmp_path / "fb" / "outbox" / "emp-1" / "evt-file_bus.json").exists()

    mcp = McpPullTransport(tmp_path / "mcp")
    assert mcp.send(_event("mcp")).ok is True
    items = mcp.drain("emp-1")
    assert [item["event_id"] for item in items] == ["evt-mcp"]
    assert mcp.drain("emp-1") == []

    routing = RoutingTransport({"file_bus": FileBusTransport(tmp_path / "routing")})
    assert routing.send(_event("file_bus")).ok is True
    unknown = routing.send(_event("mcp"))
    assert unknown.ok is False and unknown.error_code == "unknown_channel"


def test_a2a_without_endpoint_fails_fast():
    result = A2aTransport(lambda _: None).send(_event("a2a"))
    assert result.ok is False
    assert result.error_code == "endpoint_missing"


def test_retry_schedule_stops_after_max_attempts(tmp_path):
    db_path = tmp_path / "mailbus.db"
    with closing(connect(db_path)) as conn:
        apply_migrations(conn)

    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    ids = UuidGenerator()
    uow = lambda: SqliteUnitOfWork(lambda: connect(db_path), clock)
    messages = MessagingService(uow, clock, ids)
    message = messages.send(_actor(), make_send_command("会失败的消息"))
    dispatcher = Dispatcher(
        uow,
        _FailingTransport(),
        max_attempts=3,
        on_result=messages.record_delivery,
    )

    for _ in range(3):
        dispatcher.tick()
        clock.advance(seconds=10)
    assert len(messages.attempts(_actor(), message.message_id)) == 3

    clock.advance(seconds=60)
    assert dispatcher.tick() == 0
