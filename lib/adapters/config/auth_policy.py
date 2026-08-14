"""Which Agent types require browser credentials (clarify SoT)."""

from __future__ import annotations

from typing import Any


def agent_requires_browser_auth(atype: str, agent_cfg: dict[str, Any] | None = None) -> bool:
    t = (atype or "").strip()
    if t in ("hermes", "hermes_profile", "openclaw", "codex"):
        return True
    if t == "claude_code":
        cfg = agent_cfg or {}
        launch = cfg.get("launch") or {}
        if launch.get("has_browser") is False:
            return False
        kind = ((launch.get("browser") or {}).get("kind") or "").strip()
        if kind == "none":
            return False
        return True  # default: ttyd path expects basic
    return False


def agent_has_stored_browser_cred(data_dir: str, agent_id: str, agent_cfg: dict[str, Any] | None = None) -> bool:
    from lib.adapters.config.browser_auth import resolve_agent_auth

    auth = resolve_agent_auth(agent_cfg or {}, agent_id, data_dir)
    return bool(auth.get("authed"))


def raw_browser_entry_url(data_dir: str, agent_id: str, agent_cfg: dict[str, Any]) -> str:
    """Launch URL for 'obtain credential in browser' — prefer card host/port, no secret required."""
    from lib.adapters.runtime.cred_delivery import apply_instance_endpoint

    cfg = agent_cfg or {}
    atype = (cfg.get("type") or "").strip()
    launch = cfg.get("launch") or {}
    browser = dict((launch.get("browser") or {}))
    url = (browser.get("url") or "").strip()
    port = cfg.get("port")
    if port is None and isinstance(cfg.get("endpoint"), dict):
        port = cfg["endpoint"].get("port")
    if not url:
        defaults = {
            "openclaw": "http://127.0.0.1:18789/",
            "hermes": "http://127.0.0.1:9120/",
            "hermes_profile": "http://127.0.0.1:9120/",
            "codex": "http://127.0.0.1:9240/",
            "claude_code": "http://127.0.0.1:9260/",
        }
        url = defaults.get(atype, "http://127.0.0.1:9814/")
    port_fallback = {
        "hermes": "9120",
        "hermes_profile": "9120",
        "openclaw": "18789",
        "codex": "9240",
        "claude_code": "9260",
    }.get(atype, "9814")
    if port is not None and str(port).strip() != "":
        try:
            url = url.replace("{port}", str(int(port)))
        except (TypeError, ValueError):
            url = url.replace("{port}", port_fallback)
    else:
        url = url.replace("{port}", port_fallback)
    url = url.replace("{agent}", agent_id)
    return apply_instance_endpoint(cfg, url)
