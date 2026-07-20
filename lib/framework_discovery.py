"""Framework 可用性探测 — 未安装/未配置时不绑定 agent。"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .constants import MAILBUS_ROOT
from .env_bootstrap import load_mailbus_env, mailbus_paths


def _registry_path(mail_root: Path | None = None) -> Path:
    root = Path(mail_root) if mail_root else MAILBUS_ROOT
    return root / "config" / "frameworks" / "registry.json"


@lru_cache(maxsize=1)
def _load_registry_json() -> dict[str, Any]:
    path = _registry_path()
    if not path.is_file():
        return {"frameworks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"frameworks": {}}
    return data if isinstance(data, dict) else {"frameworks": {}}


_ENV_TO_PATHS_KEY = {
    "HERMES_DATA": "hermes_data",
    "OPENCODE_ROOT": "opencode_root",
    "OPENCLAW_WORKSPACE": "openclaw_workspace",
    "LINGXIAO_WORKSPACE": "lingxiao_workspace",
    "NODE_MODULES": "node_modules",
    "TEAM_PACK_ROOT": "team_pack_root",
}


def clear_framework_discovery_cache() -> None:
    _load_registry_json.cache_clear()


def _resolve_probe_path(spec: dict[str, Any], paths: dict[str, str]) -> Path | None:
    env_key = (spec.get("path_env") or "").strip()
    probe = (spec.get("probe") or "dir").strip()
    base_s = ""
    if env_key == "CLAUDE_WORKSPACE_ROOT":
        install = Path(paths["root"]).parent
        sub = probe.split(":", 1)[1] if probe.startswith("dir:") else ".mailbus/claude"
        return install / sub.replace("/", os.sep)
    paths_key = _ENV_TO_PATHS_KEY.get(env_key, "")
    base_s = os.environ.get(env_key) or (paths.get(paths_key, "") if paths_key else "")
    if not base_s:
        return None
    base = Path(base_s)
    if probe.startswith("file:"):
        rel = probe.split(":", 1)[1]
        return base / rel if rel else base
    if probe.startswith("dir:"):
        rel = probe.split(":", 1)[1]
        return base / rel if rel else base
    return base


def _probe_exists(path: Path | None, spec: dict[str, Any]) -> bool:
    if path is None:
        return False
    probe = (spec.get("probe") or "dir").strip()
    if probe.startswith("file:"):
        return path.is_file()
    return path.is_dir()


def framework_status(*, mail_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """返回各 framework 的配置/探测状态。"""
    load_mailbus_env()
    paths = mailbus_paths()
    reg = _load_registry_json().get("frameworks") or {}
    out: dict[str, dict[str, Any]] = {}
    for fw, spec in reg.items():
        if not isinstance(spec, dict):
            continue
        enabled_cfg = bool(spec.get("enabled", True))
        probe_path = _resolve_probe_path(spec, paths)
        exists = _probe_exists(probe_path, spec)
        available = enabled_cfg and exists
        reason = ""
        if not enabled_cfg:
            reason = "disabled in registry"
        elif not exists:
            reason = f"path missing: {probe_path}"
        out[fw] = {
            "framework": fw,
            "enabled": enabled_cfg,
            "available": available,
            "path": str(probe_path) if probe_path else "",
            "reason": reason,
        }
    return out


def is_framework_available(framework: str, *, mail_root: Path | None = None) -> bool:
    fw = (framework or "").strip()
    if not fw or fw == "none":
        return True
    st = framework_status(mail_root=mail_root)
    if fw not in st:
        return True
    return bool(st[fw].get("available"))


def scan_framework_agents(framework: str, *, mail_root: Path | None = None) -> list[str]:
    from .agent_registry import list_agents_by_framework

    return list_agents_by_framework(framework, mail_root=mail_root)


def doctor_framework_lines(*, mail_root: Path | None = None) -> list[str]:
    lines: list[str] = []
    for fw, st in sorted(framework_status(mail_root=mail_root).items()):
        agents = scan_framework_agents(fw, mail_root=mail_root)
        flag = "OK" if st["available"] else "SKIP"
        detail = st["reason"] or st["path"]
        lines.append(f"  {flag} {fw} agents={len(agents)} — {detail}")
    return lines
