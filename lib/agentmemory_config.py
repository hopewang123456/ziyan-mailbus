"""AgentMemory integration — access/agentmemory/integration.json + service.json (Phase 3.4)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .constants import MAILBUS_DATA_STR, MAILBUS_ROOT

DEFAULT_URL = "http://127.0.0.1:3111"
CONTAINER_URL = "http://iii-engine:3111"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=2)
def load_integration_config(mail_root_s: str = "") -> dict[str, Any]:
    root = Path(mail_root_s) if mail_root_s else MAILBUS_ROOT
    return _read_json(root / "access" / "agentmemory" / "integration.json")


@lru_cache(maxsize=2)
def load_service_config(mail_root_s: str = "") -> dict[str, Any]:
    root = Path(mail_root_s) if mail_root_s else MAILBUS_ROOT
    return _read_json(root / "access" / "agentmemory" / "service.json")


def clear_agentmemory_config_cache() -> None:
    load_integration_config.cache_clear()
    load_service_config.cache_clear()


def agentmemory_url(*, mail_root: Path | str | None = None) -> str:
    """Resolved AgentMemory HTTP base URL (config/services + env + runtime)."""
    from .service_registry import service_url

    return service_url("agentmemory", mail_root=mail_root)


def team_memory_db_path(*, mail_root: Path | str | None = None) -> str:
    env = os.environ.get("TEAM_MEMORY_DB", "").strip()
    if env:
        return env
    cfg = load_integration_config(str(mail_root or MAILBUS_ROOT))
    return (cfg.get("team_memory_db") or "").strip()


def pending_relative_dir(*, mail_root: Path | str | None = None) -> str:
    from .service_registry import service_settings

    settings = service_settings("agentmemory", mail_root=mail_root)
    bridge = settings.get("bridge") or {}
    # legacy access/agentmemory/integration.json still wins for bridge paths if present
    legacy = load_integration_config(str(mail_root or MAILBUS_ROOT))
    legacy_bridge = legacy.get("bridge") or {}
    rel = (
        (legacy_bridge.get("pending_dir") or bridge.get("pending_dir") or "store/agentmemory-pending")
        .strip()
    )
    return rel.replace("\\", "/")


def pending_dir(data_dir: str | None = None, *, mail_root: Path | str | None = None) -> Path:
    rel = pending_relative_dir(mail_root=mail_root)
    if rel.startswith("store/"):
        base = Path(data_dir or MAILBUS_DATA_STR)
        return base / rel[len("store/") :]
    root = Path(mail_root) if mail_root else MAILBUS_ROOT
    return root / rel


def bridge_env_flags(*, mail_root: Path | str | None = None) -> tuple[str, str]:
    cfg = load_integration_config(str(mail_root or MAILBUS_ROOT))
    bridge = cfg.get("bridge") or {}
    sqlite_env = (bridge.get("sqlite_env") or "MEMORY_BRIDGE_SQLITE").strip()
    am_env = (bridge.get("agentmemory_env") or "MEMORY_BRIDGE_AGENTMEMORY").strip()
    return sqlite_env, am_env
