"""CredDelivery — sync Agent card / secrets browser_auth into runtime env.

Servers differ (windows / wsl / linux / docker): compose and child processes
inherit os.environ. Call ``sync_browser_credentials_to_env`` before docker compose
or agent launch so OPENCLAW_GATEWAY_TOKEN / CODEX_UI_PASSWORD match secrets.
"""

from __future__ import annotations

import os
from typing import Any

from lib.adapters.config import token_store
from lib.infra.utils import json_read


def resolve_openclaw_token(data_dir: str) -> str:
    cred = token_store.browser_credentials(data_dir, "openclaw_gateway")
    tok = (cred.get("token") or "").strip()
    if tok:
        return tok
    try:
        from lib.adapters.config.browser_auth import openclaw_gateway_token

        return (openclaw_gateway_token() or "").strip()
    except Exception:
        return (os.environ.get("OPENCLAW_GATEWAY_TOKEN") or "").strip()


def resolve_codex_ui_password(data_dir: str, agent_id: str = "") -> str:
    """Prefer per-agent browser_auth password; else first codex agent in config."""
    if agent_id:
        cred = token_store.browser_credentials(data_dir, agent_id)
        pw = (cred.get("password") or "").strip()
        if pw:
            return pw
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = cfg.get("agents") or {}
    if isinstance(agents, dict):
        for aid, rec in agents.items():
            if not isinstance(rec, dict):
                continue
            if (rec.get("type") or "").strip() != "codex":
                continue
            cred = token_store.browser_credentials(data_dir, aid)
            pw = (cred.get("password") or "").strip()
            if pw:
                return pw
    return (os.environ.get("CODEX_UI_PASSWORD") or "").strip()


def sync_browser_credentials_to_env(data_dir: str) -> dict[str, str]:
    """Fill os.environ from secrets when env missing or still change-me.

    Returns map of env keys → source note (for logs). Does not print secrets.
    """
    applied: dict[str, str] = {}
    oc = resolve_openclaw_token(data_dir)
    cur_oc = (os.environ.get("OPENCLAW_GATEWAY_TOKEN") or "").strip()
    if oc and oc != "change-me" and (not cur_oc or cur_oc == "change-me"):
        os.environ["OPENCLAW_GATEWAY_TOKEN"] = oc
        applied["OPENCLAW_GATEWAY_TOKEN"] = "secrets.browser_auth.openclaw_gateway"

    pw = resolve_codex_ui_password(data_dir)
    cur_pw = (os.environ.get("CODEX_UI_PASSWORD") or "").strip()
    if pw and not cur_pw:
        os.environ["CODEX_UI_PASSWORD"] = pw
        applied["CODEX_UI_PASSWORD"] = "secrets.browser_auth.<codex_agent>"

    hermes = token_store.browser_credentials(data_dir, "hermes")
    ht = (hermes.get("token") or "").strip()
    cur_h = (os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN") or "").strip()
    if ht and not cur_h:
        os.environ["HERMES_DASHBOARD_SESSION_TOKEN"] = ht
        applied["HERMES_DASHBOARD_SESSION_TOKEN"] = "secrets.browser_auth.hermes"

    return applied


def apply_instance_endpoint(agent_cfg: dict[str, Any], default_url: str) -> str:
    """Rewrite launch URL host/port from agent card endpoint fields when present."""
    if not default_url:
        return default_url
    ep = agent_cfg.get("endpoint") if isinstance(agent_cfg, dict) else None
    if not isinstance(ep, dict):
        # flat fields on agent card
        host = (agent_cfg.get("host") or "").strip() if isinstance(agent_cfg, dict) else ""
        port = agent_cfg.get("port") if isinstance(agent_cfg, dict) else None
    else:
        host = (ep.get("host") or "").strip()
        port = ep.get("port")
    if not host and port is None:
        return default_url
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(default_url)
    new_host = host or parts.hostname or "127.0.0.1"
    try:
        new_port = int(port) if port is not None and str(port).strip() != "" else parts.port
    except (TypeError, ValueError):
        new_port = parts.port
    netloc = new_host if not new_port else f"{new_host}:{new_port}"
    # preserve userinfo if any
    if parts.username is not None:
        user = parts.username
        pw = parts.password
        auth = f"{user}:{pw}@" if pw is not None else f"{user}@"
        netloc = auth + netloc
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
