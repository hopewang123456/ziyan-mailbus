"""Native agent config ↔ mailbus config center (mtime-wins bidirectional)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.infra.utils import json_read, json_write


def default_native_paths(framework: str, agent_id: str = "") -> dict[str, str]:
    """Best-effort default native config file paths (editable in config center)."""
    home = Path.home()
    fw = (framework or "").replace("-", "_")
    if fw == "openclaw":
        base = os.environ.get("OPENCLAW_WORKSPACE") or str(home / "openclaw_space")
        profile = agent_id or "default"
        return {
            "config_file": str(Path(base) / f".openclaw-{profile}" / "openclaw.json")
            if agent_id
            else str(Path(base) / ".openclaw" / "openclaw.json"),
        }
    if fw == "codex":
        return {"config_file": str(home / ".codex" / "config.toml")}
    if fw == "claude_code":
        return {"config_file": str(home / f".claude-{agent_id or 'default'}" / "settings.json")}
    if fw in ("hermes", "hermes_profile"):
        hermes = os.environ.get("HERMES_DATA") or str(home / ".hermes")
        return {"config_file": str(Path(hermes) / "config.yaml")}
    if fw == "opencode":
        root = os.environ.get("OPENCODE_ROOT") or str(home / "opencode")
        return {"config_file": str(Path(root) / "opencode.json")}
    return {"config_file": ""}


def read_native_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path) if path and os.path.isfile(path) else 0.0
    except OSError:
        return 0.0


def sync_from_native_if_newer(
    mailbus_meta_path: str,
    native_path: str,
    *,
    apply_fn,
) -> str:
    """If native mtime > mailbus mirror mtime, call apply_fn(native_text) and touch meta."""
    n_m = read_native_mtime(native_path)
    m_m = read_native_mtime(mailbus_meta_path)
    if n_m <= 0:
        return "no_native"
    if n_m <= m_m:
        return "mailbus_newer_or_equal"
    try:
        text = Path(native_path).read_text(encoding="utf-8")
        apply_fn(text)
        # update meta stamp
        Path(mailbus_meta_path).parent.mkdir(parents=True, exist_ok=True)
        Path(mailbus_meta_path).write_text(str(n_m), encoding="utf-8")
        return "loaded_from_native"
    except Exception as exc:
        return f"error:{exc}"


def write_native_if_mailbus_newer(
    mailbus_meta_path: str,
    native_path: str,
    content: str,
    *,
    force: bool = False,
) -> str:
    """Write native file when user saved in config center (or force)."""
    if not native_path:
        return "no_path"
    n_m = read_native_mtime(native_path)
    m_m = read_native_mtime(mailbus_meta_path)
    if not force and n_m > m_m > 0:
        return "skipped_native_newer"
    Path(native_path).parent.mkdir(parents=True, exist_ok=True)
    Path(native_path).write_text(content, encoding="utf-8")
    Path(mailbus_meta_path).parent.mkdir(parents=True, exist_ok=True)
    Path(mailbus_meta_path).write_text(str(os.path.getmtime(native_path)), encoding="utf-8")
    return "written"


def agent_native_meta_path(data_dir: str, agent_id: str) -> str:
    return os.path.join(data_dir, "system", "native-mtime", f"{agent_id}.stamp")


def resolve_agent_native_config_path(agent_cfg: dict) -> str:
    custom = (agent_cfg.get("native_config") or {}).get("path") or agent_cfg.get("native_config_path")
    if custom:
        return str(custom)
    fw = str(agent_cfg.get("type") or agent_cfg.get("framework") or "")
    aid = str(agent_cfg.get("id") or "")
    return default_native_paths(fw, aid).get("config_file") or ""
