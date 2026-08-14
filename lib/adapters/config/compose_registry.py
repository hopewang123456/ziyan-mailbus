"""Compose 服务名解析 — transport docker 字段 → 实际 docker-compose service。

映射表 SoT：
  1. ``store/config.json → compose_registry``（本地可覆盖成真实名册/服务名）
  2. ``config/mailbus/compose-registry.json``（开源 demo seed，agent id 为通用名）

不硬编码任何个人名册。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.utils import json_read

# demo fallback（仅当配置缺失时兜底；不含个人名）
_FALLBACK_LOGICAL_TO_COMPOSE: dict[str, str] = {
    "codex-agent": "codex-web",
    "codex-review-agent": "codex-review",
    "opencode-agent": "opencode",
    "openclaw-agent": "openclaw",
    "hermes-agent": "hermes",
    "claude-agent": "",
}

_FALLBACK_AGENT_COMPOSE_SERVICE: dict[str, str] = {
    "agent-g": "codex-web",
    "agent-e": "codex-review",
    "agent-i": "opencode",
    "agent-m": "openclaw",
    "agent-l": "openclaw",
    "agent-a": "hermes",
    "agent-c": "hermes",
    "agent-b": "hermes",
    "agent-d": "hermes",
    "agent-j": "hermes",
    "agent-k": "hermes",
}

_FALLBACK_SERVICES = {
    "mailbus", "agentmemory", "hermes", "openclaw", "codex-web", "codex-review", "opencode",
}


@lru_cache(maxsize=8)
def _load_registry_cached(path: str, mtime: float) -> tuple[dict, dict, set]:
    doc = json_read(path, {})
    logical = doc.get("logical_to_compose") or {}
    agent_map = doc.get("agent_compose_service") or {}
    services = doc.get("default_services") or []
    return (
        {k: v for k, v in logical.items() if isinstance(v, str)},
        {k: v for k, v in agent_map.items() if isinstance(v, str)},
        set(services) if isinstance(services, list) else set(),
    )


def _registry(data_dir: str = "") -> tuple[dict, dict, set]:
    if data_dir:
        path = os.path.join(data_dir, "config.json")
        if os.path.isfile(path):
            try:
                mtime = os.path.getmtime(path)
                logical, agent_map, services = _load_registry_cached(path, mtime)
                if logical or agent_map:
                    return logical or dict(_FALLBACK_LOGICAL_TO_COMPOSE), (
                        agent_map or dict(_FALLBACK_AGENT_COMPOSE_SERVICE)
                    ), services or set(_FALLBACK_SERVICES)
            except OSError:
                pass
    pub = os.path.join(str(MAILBUS_ROOT), "config", "mailbus", "compose-registry.json")
    if os.path.isfile(pub):
        try:
            logical, agent_map, services = _load_registry_cached(pub, os.path.getmtime(pub))
            return (
                logical or dict(_FALLBACK_LOGICAL_TO_COMPOSE),
                agent_map or dict(_FALLBACK_AGENT_COMPOSE_SERVICE),
                services or set(_FALLBACK_SERVICES),
            )
        except OSError:
            pass
    return (
        dict(_FALLBACK_LOGICAL_TO_COMPOSE),
        dict(_FALLBACK_AGENT_COMPOSE_SERVICE),
        set(_FALLBACK_SERVICES),
    )


def resolve_compose_service(agent_id: str, docker_cfg: dict | None, data_dir: str = "") -> str:
    """返回 docker-compose.yml 中的 service 名。"""
    docker_cfg = docker_cfg or {}
    if docker_cfg.get("compose_service"):
        return str(docker_cfg["compose_service"]).strip()
    logical = (docker_cfg.get("service") or "").strip()
    logical_map, agent_map, _ = _registry(data_dir)
    if agent_id in agent_map:
        return agent_map[agent_id]
    if logical in logical_map:
        mapped = logical_map[logical]
        if mapped:
            return mapped
    if logical and logical not in logical_map:
        # already a compose name
        return logical
    return agent_id


def agent_compose_services(data_dir: str = "") -> set[str]:
    _, _, services = _registry(data_dir)
    return set(services) or set(_FALLBACK_SERVICES)


def resolve_logical_service(logical_name: str, data_dir: str = "") -> str:
    """逻辑名（codex-agent 等）→ compose service 名；缺失返回空串。"""
    logical_map, _, _ = _registry(data_dir)
    val = logical_map.get(logical_name)
    return val if isinstance(val, str) else ""


def clear_compose_registry_cache() -> None:
    _load_registry_cached.cache_clear()
