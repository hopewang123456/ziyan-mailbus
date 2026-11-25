"""大屏领域规则：在线判定、播放状态与配置校验。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from mailbus.core.collab.models import Screen
from mailbus.core.shared.errors import UnprocessableError

ONLINE_TTL = timedelta(seconds=60)
LAYOUT_TYPES = ("office", "grid", "custom")
THEMES = ("auto", "dark", "light")
RESOLUTIONS = ("1920x1080", "3840x2160")
PLAY_STATES = ("playing", "paused")
_DEFAULT_CONFIG: dict[str, Any] = {
    "layout_type": "office",
    "theme": "auto",
    "resolution": "1920x1080",
    "play_state": "playing",
}


def is_online(screen: Screen, now: datetime) -> bool:
    fresh = screen.last_seen_at is not None and now - screen.last_seen_at <= ONLINE_TTL
    return bool(screen.online and fresh)


def normalize_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """校验并补齐草稿配置；``grid`` 必须绑定团队。"""
    config = dict(_DEFAULT_CONFIG)
    config.update(raw or {})
    layout_type = _choice(config, "layout_type", LAYOUT_TYPES)
    _choice(config, "theme", THEMES)
    _choice(config, "resolution", RESOLUTIONS)
    _choice(config, "play_state", PLAY_STATES)
    team_id = _text(config.get("team_id"))
    if layout_type == "grid" and not team_id:
        raise UnprocessableError("grid 布局必须绑定团队")
    for key in ("office", "grid", "custom"):
        value = config.get(key)
        if value is not None and not isinstance(value, dict):
            raise UnprocessableError(f"config.{key} 必须是对象")
    config["team_id"] = team_id
    return config


def play_state(screen: Screen) -> str:
    """播放状态即时生效：先看草稿，再回退已发布配置。"""
    return str(screen.config.get("play_state")
               or screen.published_config.get("play_state") or "playing")


def team_bound(screen: Screen) -> bool:
    return bool(_text(screen.published_config.get("team_id")))


def published_team_id(screen: Screen) -> str | None:
    if not screen.published_config:
        return None
    return _text(screen.published_config.get("team_id"))


def public_projection(screen: Screen) -> dict[str, Any]:
    """公开配置投影：剔除 ``team_id``，只保留 ``team_bound``。"""
    config = screen.published_config or {}
    return {
        "screen_id": screen.screen_id,
        "config_version": screen.config_version,
        "published": bool(config),
        "layout_type": str(config.get("layout_type") or "office"),
        "theme": str(config.get("theme") or "auto"),
        "resolution": str(config.get("resolution") or "1920x1080"),
        "team_bound": team_bound(screen),
        "play_state": play_state(screen),
        "office": config.get("office"),
        "grid": config.get("grid"),
        "custom": config.get("custom"),
    }


def _choice(config: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = str(config.get(key) or allowed[0])
    if value not in allowed:
        raise UnprocessableError(f"不支持的 {key}：{value}")
    config[key] = value
    return value


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
