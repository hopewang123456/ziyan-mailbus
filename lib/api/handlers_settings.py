"""GET/POST /api/settings/* — Dashboard 配置中心。"""

from __future__ import annotations

import os
from typing import cast

from lib.config_admin import (
    env_status,
    get_section,
    list_sections,
    patch_env,
    patch_section,
)
from lib.domain.types import IntegrationsOverviewView, SettingsSectionsView
from lib.utils import json_read


def handle_settings_sections(handler):
    body: SettingsSectionsView = {"status": "ok", "sections": list_sections()}
    handler._send_json(body)


def handle_settings_section_get(handler, section: str):
    try:
        handler._send_json({"status": "ok", **get_section(handler.data_dir, section)})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def handle_settings_section_patch(handler, section: str):
    body = handler._read_post_body()
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
    # Optional ?persist_seed=1 for services
    if section == "services" and isinstance(patch, dict):
        qs = handler.path.split("?", 1)
        if len(qs) > 1 and "persist_seed=1" in qs[1]:
            patch = dict(patch)
            patch["persist_seed"] = True
    try:
        result, _restart = patch_section(handler.data_dir, section, patch)
        handler._send_json({"status": "ok", **result})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def handle_settings_services_probe(handler):
    """POST /api/settings/section/services/probe — lightweight connectivity check."""
    from lib.service_registry import probe_service

    cfg = json_read(os.path.join(handler.data_dir, "config.json"), {})
    body = handler._read_post_body() or {}
    names = body.get("services") or ["ollama", "agentmemory"]
    if isinstance(names, str):
        names = [names]
    probes = {}
    for name in names:
        probes[str(name)] = probe_service(str(name), config=cfg, data_dir=handler.data_dir)
    handler._send_json({"status": "ok", "probes": probes})


def handle_settings_env_get(handler):
    handler._send_json({"status": "ok", **env_status(handler.data_dir)})


def handle_settings_env_patch(handler):
    body = handler._read_post_body()
    vars_patch = body.get("vars") or body
    if not isinstance(vars_patch, dict):
        handler._send_json({"status": "error", "error": "vars must be object"}, 400)
        return
    result = patch_env(handler.data_dir, vars_patch)
    handler._send_json({"status": "ok", **result})


def handle_integrations(handler):
    """GET /api/settings/integrations — optional adapters registry (Wave4/5)."""
    from lib.application.integrations_query import integrations_overview

    overview = cast(IntegrationsOverviewView, integrations_overview(handler.data_dir))
    handler._send_json({"status": "ok", **overview})
