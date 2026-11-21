"""操作日志只读投影：直接读 outbox，不维护第二份日志表。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mailbus.application.identity.dto import Actor
from mailbus.application.queries.ports import ReadUnitOfWork
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.values import Capability


@dataclass(frozen=True, slots=True)
class LogEntryView:
    event_id: str
    kind: str
    payload: dict[str, Any]
    attempts: int
    created_at: datetime | None


class LogQuery:
    def __init__(self, uow_factory: Callable[[], ReadUnitOfWork]) -> None:
        self._uow = uow_factory

    def recent(self, actor: Actor, limit: int = 50) -> tuple[LogEntryView, ...]:
        """操作日志含全局事件负载，仅限具备 log_read 的账号查看。"""
        ensure_allowed(actor.to_subject(), Capability.LOG_READ, Resource(kind="log"))
        with self._uow() as uow:
            events = uow.outbox.recent(limit)
        return tuple(
            LogEntryView(
                event_id=event.event_id,
                kind=event.kind,
                payload=dict(event.payload),
                attempts=event.attempts,
                created_at=event.created_at,
            )
            for event in events
        )
