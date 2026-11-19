"""大屏登记、心跳、离线与遥控聚焦用例。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from mailbus.application.identity.dto import Actor
from mailbus.core.collab.models import Screen
from mailbus.core.collab.ports import CollabEventBus, CollabUnitOfWork
from mailbus.core.identity.policy import Resource, ensure_any_allowed
from mailbus.core.shared.errors import NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability

_ONLINE_TTL = timedelta(seconds=60)
_ADMIN_ACTIONS = (Capability.CONSOLE_ADMIN, Capability.TASK_DISPATCH)


@dataclass(frozen=True, slots=True)
class ScreenView:
    screen_id: str
    name: str
    floor_id: str | None
    seat_id: str | None
    online: bool
    last_seen: datetime | None


@dataclass(frozen=True, slots=True)
class RegisterScreenCommand:
    screen_id: str | None
    name: str
    floor_id: str | None = None
    seat_id: str | None = None


class ScreenService:
    def __init__(
        self,
        uow_factory: Callable[[], CollabUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        events: CollabEventBus,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._events = events

    def list_screens(self) -> tuple[ScreenView, ...]:
        now = self._clock.now()
        with self._uow() as uow:
            records = uow.screens.list_all()
        return tuple(_view(record, now) for record in records)

    def register(
        self, actor: Actor | None, cmd: RegisterScreenCommand
    ) -> ScreenView:
        if actor is not None:
            self._ensure_admin(actor)
        now = self._clock.now()
        screen_id = (cmd.screen_id or "").strip() or self._ids.new("screen")
        with self._uow() as uow:
            existing = uow.screens.get(screen_id)
            screen = Screen(
                screen_id=screen_id,
                name=cmd.name,
                floor_id=cmd.floor_id,
                seat_id=cmd.seat_id,
                online=True,
                last_seen_at=now,
                created_at=existing.created_at if existing else now,
            )
            uow.screens.save(screen)
            uow.commit()
        self._events.publish(
            "screen.registered",
            {
                "screen_id": screen.screen_id,
                "name": screen.name,
                "floor_id": screen.floor_id,
                "at": now.isoformat(),
            },
        )
        return _view(screen, now)

    def heartbeat(
        self, screen_id: str, floor_id: str | None, seat_id: str | None
    ) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            screen = uow.screens.get(screen_id)
            if screen is None:
                raise NotFoundError("大屏不存在")
            uow.screens.save(
                Screen(
                    screen_id=screen.screen_id,
                    name=screen.name,
                    floor_id=floor_id,
                    seat_id=seat_id,
                    online=True,
                    last_seen_at=now,
                    created_at=screen.created_at,
                )
            )
            uow.commit()

    def leave(self, screen_id: str) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            screen = uow.screens.get(screen_id)
            if screen is None:
                return
            uow.screens.save(
                Screen(
                    screen_id=screen.screen_id,
                    name=screen.name,
                    floor_id=screen.floor_id,
                    seat_id=screen.seat_id,
                    online=False,
                    last_seen_at=now,
                    created_at=screen.created_at,
                )
            )
            uow.commit()

    def focus(
        self, actor: Actor, screen_id: str, floor_id: str, seat_id: str | None
    ) -> None:
        self._ensure_admin(actor)
        with self._uow() as uow:
            if uow.screens.get(screen_id) is None:
                raise NotFoundError("大屏不存在")
        self._events.publish(
            "screen.focus",
            {
                "screen_id": screen_id,
                "floor_id": floor_id,
                "seat_id": seat_id,
                "at": self._clock.now().isoformat(),
            },
        )

    @staticmethod
    def _ensure_admin(actor: Actor) -> None:
        ensure_any_allowed(actor.to_subject(), _ADMIN_ACTIONS, Resource(kind="screen"))


def _view(screen: Screen, now: datetime) -> ScreenView:
    fresh = (
        screen.last_seen_at is not None
        and now - screen.last_seen_at <= _ONLINE_TTL
    )
    return ScreenView(
        screen_id=screen.screen_id,
        name=screen.name,
        floor_id=screen.floor_id,
        seat_id=screen.seat_id,
        online=bool(screen.online and fresh),
        last_seen=screen.last_seen_at,
    )
