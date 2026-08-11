"""Container name resolution — extracted from frameworks/registry (Wave 1 D8)."""
from __future__ import annotations

import os


def container_prefix() -> str:
    return os.environ.get("MAILBUS_CONTAINER_PREFIX", "docker-agents")


def container_for_service(service: str) -> str:
    env_key = f"MAILBUS_CONTAINER_{service.upper().replace('-', '_')}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    return f"{container_prefix()}-{service}-1"


def resolve_container(agent_cfg: dict, agent_name: str, default_service: str) -> str:
    docker_cfg = agent_cfg.get("docker") or {}
    if docker_cfg.get("container"):
        return docker_cfg["container"]
    env_key = f"MAILBUS_CONTAINER_{agent_name.upper()}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    from lib.adapters.config.compose_registry import resolve_compose_service

    # 逻辑名 codex-agent/opencode-agent → 实际 compose service（lingxiao/dali）
    resolved = resolve_compose_service(agent_name, docker_cfg)
    if not resolved or resolved == agent_name:
        fallback = (docker_cfg.get("service") or default_service or agent_name or "").strip()
        if fallback and fallback != agent_name:
            resolved = resolve_compose_service(agent_name, {"service": fallback}) or fallback
        else:
            resolved = resolved or fallback or agent_name
    return container_for_service(resolved)
