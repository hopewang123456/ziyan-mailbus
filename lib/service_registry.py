"""External service registry — config-driven URLs for ollama / agentmemory / ….

Priority: explicit env > store config.services > config/services/*.json > code fallback.
Runtime profiles: windows | wsl | docker.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .constants import MAILBUS_ROOT

RuntimeName = str  # windows | wsl | docker

_FALLBACK = {
    "ollama": {
        "id": "ollama",
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "timeout_seconds": 60,
        "env_base_url": "MAILBUS_OLLAMA_BASE_URL",
        "env_model": "MAILBUS_OLLAMA_MODEL",
        "profiles": {
            "windows": {"base_url": "http://127.0.0.1:11434"},
            "wsl": {
                "base_url": "http://127.0.0.1:11435",
                "proxy": {
                    "listen_host": "0.0.0.0",
                    "listen_port": 11435,
                    "target": "http://127.0.0.1:11434",
                },
            },
            "docker": {"base_url": "http://host.docker.internal:11435"},
        },
    },
    "agentmemory": {
        "id": "agentmemory",
        "health_path": "/agentmemory/health",
        "env_base_url": "AGENTMEMORY_URL",
        "profiles": {
            "windows": {"base_url": "http://127.0.0.1:3111"},
            "wsl": {"base_url": "http://127.0.0.1:3111"},
            "docker": {"base_url": "http://iii-engine:3111"},
        },
    },
}


def clear_service_registry_cache() -> None:
    load_services_seed.cache_clear()


def detect_runtime() -> RuntimeName:
    """Detect where this process runs: docker container, WSL, or Windows/other host."""
    from .platform_runner import running_in_mailbus_docker

    if running_in_mailbus_docker() or os.path.isdir("/mailbus") and os.path.exists("/.dockerenv"):
        return "docker"
    if sys.platform == "win32":
        return "windows"
    # Linux: WSL vs native
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            if "microsoft" in fh.read().lower():
                return "wsl"
    except OSError:
        pass
    # Native Linux host talking to Docker-published ports — treat like wsl profile
    # (localhost services) unless MAILBUS_RUNTIME overrides.
    override = (os.environ.get("MAILBUS_RUNTIME") or "").strip().lower()
    if override in ("windows", "wsl", "docker"):
        return override
    return "wsl"


@lru_cache(maxsize=4)
def load_services_seed(mail_root_s: str = "") -> dict[str, Any]:
    root = Path(mail_root_s) if mail_root_s else MAILBUS_ROOT
    services_dir = root / "config" / "services"
    out: dict[str, Any] = {}
    if not services_dir.is_dir():
        return {k: dict(v) for k, v in _FALLBACK.items()}
    for name in ("ollama", "agentmemory"):
        path = services_dir / f"{name}.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    out[name] = data
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        out[name] = dict(_FALLBACK.get(name) or {})
    return out


def _read_store_services(config: Optional[dict], data_dir: str = "") -> dict[str, Any]:
    if config and isinstance(config.get("services"), dict):
        return dict(config["services"])
    if data_dir:
        from .utils import json_read

        root = json_read(os.path.join(data_dir, "config.json"), {})
        return dict(root.get("services") or {})
    return {}


def service_block(
    name: str,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    mail_root: Path | str | None = None,
) -> dict[str, Any]:
    """Merged service definition for ``name`` (ollama / agentmemory)."""
    seed = load_services_seed(str(mail_root or MAILBUS_ROOT))
    base = dict(_FALLBACK.get(name) or {})
    base.update(seed.get(name) or {})
    store = _read_store_services(config, data_dir)
    stored = store.get(name)
    if isinstance(stored, dict):
        # deep-ish merge profiles
        merged = dict(base)
        for k, v in stored.items():
            if k == "profiles" and isinstance(v, dict):
                profiles = dict(merged.get("profiles") or {})
                for pk, pv in v.items():
                    if isinstance(pv, dict) and isinstance(profiles.get(pk), dict):
                        profiles[pk] = {**profiles[pk], **pv}
                    else:
                        profiles[pk] = pv
                merged["profiles"] = profiles
            else:
                merged[k] = v
        return merged
    return base


def service_settings(
    name: str,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    runtime: Optional[RuntimeName] = None,
    mail_root: Path | str | None = None,
    ignore_env: bool = False,
) -> dict[str, Any]:
    """Resolved settings for current (or given) runtime.

    When ``ignore_env`` is True (compose sync / docker profile injection), skip
    host env overrides so localhost .env values cannot poison container URLs.
    """
    block = service_block(name, config=config, data_dir=data_dir, mail_root=mail_root)
    rt = runtime or detect_runtime()
    profiles = block.get("profiles") or {}
    profile = dict(profiles.get(rt) or profiles.get("windows") or {})

    env_url_key = (block.get("env_base_url") or "").strip()
    env_model_key = (block.get("env_model") or "").strip()
    base_url = ""
    if not ignore_env and env_url_key:
        base_url = (os.environ.get(env_url_key) or "").strip()
    if not base_url:
        base_url = (profile.get("base_url") or "").strip()
    if not base_url:
        base_url = ((profiles.get("windows") or {}).get("base_url") or "").strip()

    model = ""
    if not ignore_env and env_model_key:
        model = (os.environ.get(env_model_key) or "").strip()
    if not model:
        model = (block.get("model") or block.get("default_model") or "").strip()

    out: dict[str, Any] = {
        "id": block.get("id") or name,
        "kind": block.get("kind") or name,
        "runtime": rt,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "timeout_seconds": int(block.get("timeout_seconds") or profile.get("timeout_seconds") or 60),
        "health_path": block.get("health_path") or "",
        "proxy": dict(profile.get("proxy") or {}),
        "profiles": profiles,
        "env_base_url": env_url_key,
        "env_model": env_model_key,
    }
    if name == "ollama":
        out["temperature"] = block.get("temperature", 0.1)
        out["max_tokens"] = block.get("max_tokens", 1024)
        out["default_model"] = block.get("default_model") or model
    if name == "agentmemory":
        out["bridge"] = dict(block.get("bridge") or {})
    return out


def service_url(
    name: str,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    runtime: Optional[RuntimeName] = None,
    mail_root: Path | str | None = None,
    ignore_env: bool = False,
) -> str:
    return service_settings(
        name,
        config=config,
        data_dir=data_dir,
        runtime=runtime,
        mail_root=mail_root,
        ignore_env=ignore_env,
    )["base_url"]


def compose_env_for_services(
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    mail_root: Path | str | None = None,
) -> dict[str, str]:
    """Env vars for Docker Compose / containers (always docker profile)."""
    ollama = service_settings(
        "ollama",
        config=config,
        data_dir=data_dir,
        runtime="docker",
        mail_root=mail_root,
        ignore_env=True,
    )
    am = service_settings(
        "agentmemory",
        config=config,
        data_dir=data_dir,
        runtime="docker",
        mail_root=mail_root,
        ignore_env=True,
    )
    env: dict[str, str] = {
        "MAILBUS_OLLAMA_BASE_URL": ollama["base_url"],
        "MAILBUS_OLLAMA_MODEL": ollama.get("model") or "qwen2.5:3b-instruct-q4_K_M",
        "AGENTMEMORY_URL": am["base_url"],
    }
    return env


def ollama_proxy_listen(
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
) -> tuple[str, int, str]:
    """Return (listen_host, listen_port, target_url) for WSL ollama proxy."""
    settings = service_settings("ollama", config=config, data_dir=data_dir, runtime="wsl")
    proxy = settings.get("proxy") or {}
    host = str(proxy.get("listen_host") or "0.0.0.0")
    port = int(proxy.get("listen_port") or os.environ.get("OLLAMA_WSL_PROXY_PORT") or 11435)
    target = str(proxy.get("target") or "http://127.0.0.1:11434").rstrip("/")
    # env overrides
    if os.environ.get("OLLAMA_WSL_PROXY_TARGET"):
        target = os.environ["OLLAMA_WSL_PROXY_TARGET"].rstrip("/")
    if os.environ.get("OLLAMA_WSL_PROXY_PORT"):
        port = int(os.environ["OLLAMA_WSL_PROXY_PORT"])
    return host, port, target


def probe_service(
    name: str,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    timeout: int = 5,
) -> dict[str, Any]:
    """Lightweight HTTP readiness probe."""
    settings = service_settings(name, config=config, data_dir=data_dir)
    base = settings["base_url"]
    if not base:
        return {"ok": False, "id": name, "error": "missing base_url"}
    if name == "ollama":
        from .internal_llm.probe import _probe_ollama

        return _probe_ollama(
            {
                "base_url": base,
                "model": settings.get("model") or "",
                "timeout_seconds": min(timeout, int(settings.get("timeout_seconds") or 10)),
            }
        )
    path = settings.get("health_path") or "/health"
    url = f"{base}{path if path.startswith('/') else '/' + path}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = 200 <= int(resp.status) < 300
        return {"ok": ok, "id": name, "base_url": base, "health_url": url}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"ok": False, "id": name, "base_url": base, "health_url": url, "error": str(exc)}
