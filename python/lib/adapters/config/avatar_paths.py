"""Resolve agent portrait / animated avatar paths from Agent card + defaults."""

from __future__ import annotations

import os
from typing import Any

from lib.infra.constants import MAILBUS_DOCS_ROOT_STR, MAILBUS_ROOT
from lib.infra.utils import json_read


def default_avatar_roots() -> list[str]:
    return [
        os.path.join(str(MAILBUS_ROOT), "web", "public", "avatars"),
        os.path.join(MAILBUS_DOCS_ROOT_STR, "avatars"),
    ]


def default_portrait_path(agent_id: str) -> str:
    for root in default_avatar_roots():
        for name in (f"{agent_id}_portrait.png", f"{agent_id}_portrait.svg"):
            p = os.path.join(root, name)
            if os.path.isfile(p):
                return p
    return os.path.join(default_avatar_roots()[0], f"{agent_id}_portrait.png")


def default_animated_path(agent_id: str) -> str:
    for root in default_avatar_roots():
        for name in (f"{agent_id}_animated.webp", f"{agent_id}_animated.svg"):
            p = os.path.join(root, name)
            if os.path.isfile(p):
                return p
    return os.path.join(default_avatar_roots()[0], f"{agent_id}_animated.webp")


def card_paths(agent_cfg: dict | None) -> dict[str, str]:
    if not isinstance(agent_cfg, dict):
        return {}
    raw = agent_cfg.get("paths")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(v, str) and v.strip():
            out[str(k)] = v.strip()
    return out


def resolve_portrait_file(agent_id: str, agent_cfg: dict | None = None) -> str:
    paths = card_paths(agent_cfg)
    for key in ("portrait", "avatar_portrait", "avatar"):
        p = paths.get(key) or ""
        if p and os.path.isfile(p):
            return p
    return default_portrait_path(agent_id)


def resolve_animated_file(agent_id: str, agent_cfg: dict | None = None) -> str:
    paths = card_paths(agent_cfg)
    for key in ("avatar_animated", "animated", "portrait_animated"):
        p = paths.get(key) or ""
        if p and os.path.isfile(p):
            return p
    return default_animated_path(agent_id)


def public_avatar_url(abs_path: str, *, kind: str, agent_id: str) -> str:
    """Prefer /avatars/… when under public; else API stream URL."""
    if not abs_path:
        return f"/api/agent-avatar/{agent_id}/{kind}"
    norm = os.path.normpath(abs_path)
    for root in default_avatar_roots():
        root_n = os.path.normpath(root)
        if norm.lower().startswith(root_n.lower() + os.sep) or norm.lower() == root_n.lower():
            rel = os.path.relpath(norm, root_n).replace("\\", "/")
            return f"avatars/{rel}"
    return f"/api/agent-avatar/{agent_id}/{kind}"


def resolve_avatar_urls(agent_id: str, agent_cfg: dict | None = None) -> dict[str, Any]:
    portrait = resolve_portrait_file(agent_id, agent_cfg)
    animated = resolve_animated_file(agent_id, agent_cfg)
    return {
        "avatar_url": public_avatar_url(portrait, kind="portrait", agent_id=agent_id),
        "avatar_animated": public_avatar_url(animated, kind="animated", agent_id=agent_id),
        "portrait_path": portrait,
        "animated_path": animated,
        "portrait_exists": os.path.isfile(portrait),
        "animated_exists": os.path.isfile(animated),
    }


def ensure_default_portrait_paths(cfg: dict) -> dict:
    """Fill missing paths.portrait / paths.avatar_animated on agents (idempotent)."""
    agents = cfg.get("agents") or {}
    if not isinstance(agents, dict):
        return cfg
    for aid, rec in agents.items():
        if not isinstance(rec, dict):
            continue
        paths = dict(rec.get("paths") or {}) if isinstance(rec.get("paths"), dict) else {}
        if not (paths.get("portrait") or "").strip():
            paths["portrait"] = default_portrait_path(aid)
        if not (paths.get("avatar_animated") or "").strip():
            paths["avatar_animated"] = default_animated_path(aid)
        rec["paths"] = paths
        rec["custom_paths"] = True
        agents[aid] = rec
    cfg["agents"] = agents
    return cfg
