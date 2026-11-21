"""B4 集成：审批超时用假时钟验证，不 sleep。"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

from mailbus.adapters.persistence.sqlite.connection import connect
from mailbus.adapters.persistence.sqlite.migrations import apply_migrations
from mailbus.adapters.persistence.sqlite.uow import SqliteUnitOfWork
from mailbus.adapters.system.ids import UuidGenerator
from mailbus.adapters.transport.collab_bus import InProcessEventBus
from mailbus.application.approval.dto import make_approval_command
from mailbus.application.approval.service import ApprovalService
from mailbus.application.dispatch.dispatcher import Dispatcher
from mailbus.application.identity.dto import Actor
from mailbus.application.workflow.dto import make_advance_command, make_task_command
from mailbus.application.workflow.tasks import TaskService
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.events import DeliveryResult
from mailbus.core.shared.values import Capability, DataScope


class _FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta) -> None:
        self._now += timedelta(**delta)


class _OkTransport:
    def send(self, event):
        return DeliveryResult(ok=True)


def _actor() -> Actor:
    return Actor(
        employee_id="emp-test",
        account_type=AccountType.HUMAN,
        status=EmployeeStatus.ACTIVE,
        capabilities=frozenset({Capability.ALL}),
        data_scope=DataScope.GLOBAL,
    )


def test_blocking_approval_times_out_and_keeps_task_blocked(tmp_path):
    db_path = tmp_path / "mailbus.db"
    with closing(connect(db_path)) as conn:
        apply_migrations(conn)

    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    ids = UuidGenerator()
    uow = lambda: SqliteUnitOfWork(lambda: connect(db_path), clock)
    tasks = TaskService(uow, clock, ids, InProcessEventBus())
    approvals = ApprovalService(uow, clock, ids)
    actor = _actor()

    task = tasks.create(actor, make_task_command("需要审批"))
    tasks.dispatch(actor, task.task_id)
    tasks.advance(actor, task.task_id, make_advance_command(None, "running"))

    approval = approvals.request(
        actor,
        make_approval_command(
            task.task_id, "请确认", "blocking", timeout_minutes=30
        ),
    )
    assert tasks.get(task.task_id).state == "blocked"
    assert approval.status == "pending"

    clock.advance(minutes=31)
    dispatcher = Dispatcher(
        uow, _OkTransport(), sweeper=approvals.sweep_expired
    )
    dispatcher.tick()

    expired = approvals.get(actor, approval.approval_id)
    assert expired.status == "expired"
    assert tasks.get(task.task_id).state == "blocked"
    assert approvals.sweep_expired() == 0
