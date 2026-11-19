"""领域事件 → outbox 行（与业务状态变更同一事务）。

跨上下文共用的用例层工具；不依赖任何具体上下文。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from mailbus.core.shared.events import DomainEvent, OutboxEvent
from mailbus.core.shared.ports import IdGenerator, OutboxPort


def enqueue_events(
    outbox: OutboxPort,
    events: Iterable[DomainEvent],
    ids: IdGenerator,
    now: datetime,
) -> None:
    for event in events:
        outbox.enqueue(
            OutboxEvent(
                event_id=ids.new("evt"),
                kind=event.kind,
                payload=dict(event.payload),
                due_at=now,
            )
        )
