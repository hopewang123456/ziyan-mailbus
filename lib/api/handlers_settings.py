"""GET/POST /api/settings/* — Dashboard 配置中心。"""

from __future__ import annotations

import os
from typing import cast

from lib.adapters.config.config_admin import (
    env_status,
    get_section,
    list_sections,
    patch_env,
    patch_section,
)
from lib.domain.types import IntegrationsOverviewView, SettingsSectionsView
from lib.infra.utils import json_read


def handle_settings_sections(handler):
    body: SettingsSectionsView = {"status": "ok", "sections": list_sections()}
    handler._send_json(body)


def handle_settings_paths(handler):
    """GET /api/settings/paths — vault/team-pack roots + compose_override (read-only)."""
    from lib.infra.env_bootstrap import mailbus_paths

    paths = mailbus_paths()
    handler._send_json({
        "status": "ok",
        "paths": paths,
        "compose_override": paths.get("compose_override", ""),
        "note": "MAILBUS_*_ROOT / TEAM_PACK_* / MAILBUS_COMPOSE_DIR|OVERRIDE configure these",
    })


def handle_skills_index(handler):
    """GET /api/skills/index — skills-index (agents/reverse/orphans) from person-index frontmatter."""
    from lib.adapters.config.sync_layers import build_skills_index_from_registry
    from lib.adapters.config.agent_registry import mailbus_root

    root = mailbus_root(handler.data_dir)
    index = build_skills_index_from_registry(mail_root=root)
    handler._send_json({"status": "ok", "index": index})


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
    from lib.adapters.ops.service_registry import probe_service

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
    """GET/POST /api/settings/integrations — list adapters; POST add/remove plugin specs."""
    from lib.application.integrations_query import integrations_overview
    from lib.adapters.config.config_admin import config_path
    from lib.infra.utils import json_read, json_write

    if handler.command == "POST":
        body = handler._read_post_body() or {}
        action = str(body.get("action") or "add_plugin").strip()
        spec = str(body.get("spec") or "").strip()
        if action in ("add_plugin", "remove_plugin") and not spec:
            handler._send_json({"status": "error", "error": "spec required (module or module:attr)"}, 400)
            return
        cfg_path = config_path(handler.data_dir)
        cfg = json_read(cfg_path, {})
        integ = dict(cfg.get("integrations") or {})
        plugins = list(integ.get("plugins") or [])
        if action == "add_plugin":
            if spec not in plugins:
                plugins.append(spec)
            integ["plugins"] = plugins
            cfg["integrations"] = integ
            json_write(cfg_path, cfg)
            try:
                from lib.adapters.integrations.entry_point_discovery import reload_integration_plugins

                loaded = reload_integration_plugins(data_dir=handler.data_dir, config=cfg)
            except Exception as exc:
                handler._send_json({"status": "error", "error": f"saved but reload failed: {exc}"}, 500)
                return
            handler._send_json({"status": "ok", "plugins": plugins, "loaded": loaded})
            return
        if action == "remove_plugin":
            plugins = [p for p in plugins if p != spec]
            integ["plugins"] = plugins
            cfg["integrations"] = integ
            json_write(cfg_path, cfg)
            handler._send_json({"status": "ok", "plugins": plugins})
            return
        handler._send_json({"status": "error", "error": f"unknown action: {action}"}, 400)
        return

    overview = cast(IntegrationsOverviewView, integrations_overview(handler.data_dir))
    cfg = json_read(config_path(handler.data_dir), {})
    plugins = list(((cfg.get("integrations") or {}).get("plugins")) or [])
    handler._send_json({"status": "ok", **overview, "plugins": plugins})
