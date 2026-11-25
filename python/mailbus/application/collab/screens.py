"""大屏登记、心跳、配置草稿/发布、聚焦与删除用例。"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from mailbus.application.identity.dto import Actor
from mailbus.core.collab.models import Screen
from mailbus.core.collab.ports import CollabEventBus, CollabUnitOfWork
from mailbus.core.collab.rules import (
    is_online,
    normalize_config,
    play_state,
    public_projection,
    published_team_id,
    team_bound,
)
from mailbus.core.identity.policy import Resource, ensure_any_allowed
from mailbus.core.shared.errors import (
    CapacityError,
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    UnprocessableError,
    VersionConflictError,
)
from mailbus.core.shared.ports import (
    Clock,
    IdGenerator,
    RateLimiterPort,
    SecretHasherPort,
)
from mailbus.core.shared.values import Capability

_ADMIN_ACTIONS = (Capability.CONSOLE_ADMIN,)


def _new_secret() -> str:
    return secrets.token_urlsafe(24)


@dataclass(frozen=True, slots=True)
class ScreenView:
    screen_id: str
    name: str
    source: str
    online: bool
    last_seen_at: datetime | None
    config_version: int
    published_config_version: int | None
    team_bound: bool
    play_state: str


@dataclass(frozen=True, slots=True)
class ScreenConfigView:
    screen_id: str
    config_version: int
    published_config_version: int | None
    updated_at: datetime | None
    play_state: str
    config: dict


@dataclass(frozen=True, slots=True)
class PublicScreenConfigView:
    screen_id: str
    config_version: int
    published: bool
    layout_type: str
    theme: str
    resolution: str
    team_bound: bool
    play_state: str
    office: dict | None = None
    grid: dict | None = None
    custom: dict | None = None


@dataclass(frozen=True, slots=True)
class RegisterScreenCommand:
    screen_id: str | None = None
    secret: str | None = None
    name: str | None = None
    floor_id: str | None = None
    seat_id: str | None = None


@dataclass(frozen=True, slots=True)
class ScreenDraftCommand:
    config: dict | None = None
    play_state: str | None = None


class ScreenService:
    def __init__(
        self,
        uow_factory: Callable[[], CollabUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        events: CollabEventBus,
        limiter: RateLimiterPort,
        hasher: SecretHasherPort,
        max_public_screens: int = 64,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._events = events
        self._limiter = limiter
        self._hasher = hasher
        self._max_public_screens = max_public_screens

    # ---- 管理端 ----

    def list_page(
        self, actor: Actor, limit: int, offset: int
    ) -> tuple[tuple[ScreenView, ...], int]:
        self._ensure_admin(actor)
        now = self._clock.now()
        with self._uow() as uow:
            records = uow.screens.list_page(limit, offset)
            total = uow.screens.count()
        return tuple(_view(record, now) for record in records), total

    def get_config(self, actor: Actor, screen_id: str) -> ScreenConfigView:
        self._ensure_admin(actor)
        with self._uow() as uow:
            return _config_view(_require(uow.screens.get(screen_id)))

    def save_draft(
        self, actor: Actor, screen_id: str, cmd: ScreenDraftCommand
    ) -> ScreenConfigView:
        self._ensure_admin(actor)
        now = self._clock.now()
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
            config = normalize_config(cmd.config) if cmd.config is not None else dict(
                screen.config
            )
            if cmd.play_state is not None:
                config = normalize_config({**config, "play_state": cmd.play_state})
            updated = replace(
                screen, config=config, source="manual", updated_at=now
            )
            uow.screens.save(updated)
            uow.audit.record(
                actor.employee_id, "screen.draft_saved", screen_id,
                {"config_version": updated.config_version},
            )
            uow.commit()
            return _config_view(updated)

    def publish(self, actor: Actor, screen_id: str, expected_version: int) -> tuple[int, datetime]:
        self._ensure_admin(actor)
        now = self._clock.now()
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
            if expected_version != screen.config_version:
                raise VersionConflictError("屏幕配置已被他人修改，请刷新后重试")
            if not screen.config:
                raise UnprocessableError("没有可发布的布局")
            updated = replace(
                screen,
                published_config=dict(screen.config),
                config_version=screen.config_version + 1,
                updated_at=now,
            )
            uow.screens.save(updated)
            uow.audit.record(
                actor.employee_id, "screen.published", screen_id,
                {"config_version": updated.config_version},
            )
            uow.commit()
        self._events.publish(
            "screen.config",
            {"screen_id": screen_id, "config_version": updated.config_version,
             "at": now.isoformat()},
        )
        return updated.config_version, now

    def focus(
        self, actor: Actor, screen_id: str, floor_id: str, seat_id: str | None
    ) -> None:
        self._ensure_admin(actor)
        now = self._clock.now()
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
            if not is_online(screen, now):
                raise InvalidStateError("屏幕离线，无法聚焦")
        self._events.publish(
            "screen.focus",
            {"screen_id": screen_id, "floor_id": floor_id, "seat_id": seat_id,
             "at": now.isoformat()},
        )

    def delete(self, actor: Actor, screen_id: str) -> None:
        self._ensure_admin(actor)
        now = self._clock.now()
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
            if is_online(screen, now):
                raise InvalidStateError("屏幕正在播放，无法删除")
            uow.screens.delete(screen_id)
            uow.audit.record(actor.employee_id, "screen.deleted", screen_id, {})
            uow.commit()

    # ---- 公开端 ----

    def register(self, ip: str, cmd: RegisterScreenCommand) -> tuple[ScreenView, str | None]:
        self._check_limit(f"register:{ip}")
        now = self._clock.now()
        with self._uow() as uow:
            reused = self._reusable(uow, cmd)
            if reused is not None:
                screen = replace(reused, online=True, last_seen_at=now)
                uow.screens.save(screen)
                uow.commit()
                return _view(screen, now), None
            self._ensure_capacity(uow, now)
            secret = _new_secret()
            screen = Screen(
                screen_id=self._ids.new("screen"),
                name=(cmd.name or "").strip()[:64] or "未命名大屏",
                source="auto",
                online=True,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
                secret_hash=self._hasher.digest(secret),
            )
            uow.screens.save(screen)
            uow.commit()
        self._events.publish(
            "screen.registered",
            {"screen_id": screen.screen_id, "name": screen.name, "at": now.isoformat()},
        )
        return _view(screen, now), secret

    def heartbeat(self, ip: str, screen_id: str, secret: str | None) -> None:
        self._check_limit(f"heartbeat:{ip}")
        now = self._clock.now()
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
            self._ensure_secret(screen, secret)
            uow.screens.save(replace(screen, online=True, last_seen_at=now))
            uow.commit()

    def leave(self, ip: str, screen_id: str, secret: str | None) -> None:
        self._check_limit(f"leave:{ip}")
        now = self._clock.now()
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
            self._ensure_secret(screen, secret)
            uow.screens.save(replace(screen, online=False, last_seen_at=now))
            uow.commit()

    def public_config(self, screen_id: str) -> PublicScreenConfigView:
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
        return PublicScreenConfigView(**public_projection(screen))

    def published_team_id(self, screen_id: str) -> str | None:
        with self._uow() as uow:
            screen = _require(uow.screens.get(screen_id))
        return published_team_id(screen)

    # ---- 内部 ----

    def prune_stale(self, now: datetime, days: int = 30) -> int:
        """清理从未被接管且长期离线的自动登记屏幕。"""
        cutoff = now - timedelta(days=days)
        removed = 0
        with self._uow() as uow:
            for screen in uow.screens.list_all():
                if screen.source != "auto":
                    continue
                seen = screen.last_seen_at or screen.created_at
                if seen < cutoff:
                    uow.screens.delete(screen.screen_id)
                    removed += 1
            if removed:
                uow.commit()
        return removed

    def _check_limit(self, key: str) -> None:
        if not self._limiter.allow(key):
            raise RateLimitedError("大屏请求过于频繁，请稍后再试")

    def _ensure_capacity(self, uow: CollabUnitOfWork, now: datetime) -> None:
        online = sum(1 for record in uow.screens.list_all() if is_online(record, now))
        if online >= self._max_public_screens:
            raise CapacityError("公开大屏数量已达上限，请联系管理员")

    @staticmethod
    def _ensure_admin(actor: Actor) -> None:
        ensure_any_allowed(actor.to_subject(), _ADMIN_ACTIONS, Resource(kind="screen"))


    def _reusable(
        self, uow: CollabUnitOfWork, cmd: RegisterScreenCommand
    ) -> Screen | None:
        if not cmd.screen_id or not cmd.secret:
            return None
        candidate = uow.screens.get(cmd.screen_id.strip())
        if candidate is None or not self._hasher.verify(candidate.secret_hash, cmd.secret):
            return None
        return candidate

    def _ensure_secret(self, screen: Screen, secret: str | None) -> None:
        if not self._hasher.verify(screen.secret_hash, secret):
            raise PermissionDeniedError("大屏密钥无效")


def _require(screen: Screen | None) -> Screen:
    if screen is None:
        raise NotFoundError("大屏不存在")
    return screen


def _view(screen: Screen, now: datetime) -> ScreenView:
    published = bool(screen.published_config)
    return ScreenView(
        screen_id=screen.screen_id,
        name=screen.name,
        source=screen.source,
        online=is_online(screen, now),
        last_seen_at=screen.last_seen_at,
        config_version=screen.config_version,
        published_config_version=screen.config_version if published else None,
        team_bound=team_bound(screen),
        play_state=play_state(screen),
    )


def _config_view(screen: Screen) -> ScreenConfigView:
    return ScreenConfigView(
        screen_id=screen.screen_id,
        config_version=screen.config_version,
        published_config_version=(
            screen.config_version if screen.published_config else None
        ),
        updated_at=screen.updated_at,
        play_state=play_state(screen),
        config=dict(screen.config),
    )
