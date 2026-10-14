"""GET/POST /api/settings/* — Dashboard 配置中心。"""

from __future__ import annotations

import os
from typing import cast

# 跨层解耦：api→adapter 通过 composition 拿服务（2026-09 治理）
from lib.composition import (
    config_env_status,
    config_get_section,
    config_list_sections,
    config_patch_env,
    config_patch_section,
)
from lib.domain.types import IntegrationsOverviewView, SettingsSectionsView
from lib.infra.utils import json_read


def handle_settings_sections(handler):
    body: SettingsSectionsView = {"status": "ok", "sections": config_list_sections()}
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
    # 跨层解耦：api→adapter 通过 composition 拿服务
    from lib.composition import build_skills_index_from_registry, config_mailbus_root

    root = config_mailbus_root(handler.data_dir)
    index = build_skills_index_from_registry(mail_root=root)
    handler._send_json({"status": "ok", "index": index})


def handle_settings_section_get(handler, section: str):
    try:
        handler._send_json({"status": "ok", **config_get_section(handler.data_dir, section)})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def handle_settings_section_patch(handler, section: str):
    body = handler._read_post_body()
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
    auto_discover = True
    if isinstance(body, dict) and "auto_discover_roles" in body:
        auto_discover = bool(body.get("auto_discover_roles"))
    elif isinstance(patch, dict) and "auto_discover_roles" in patch:
        auto_discover = bool(patch.pop("auto_discover_roles"))
    # Optional ?persist_seed=1 for services
    if section == "services" and isinstance(patch, dict):
        qs = handler.path.split("?", 1)
        if len(qs) > 1 and "persist_seed=1" in qs[1]:
            patch = dict(patch)
            patch["persist_seed"] = True
    try:
        result, _restart = config_patch_section(handler.data_dir, section, patch)
        effects = list(result.get("effects") or [])
        if auto_discover and section in ("agents", "frameworks"):
            effects.extend(_try_auto_discover_roles(handler.data_dir))
        result["effects"] = effects
        handler._send_json({"status": "ok", **result})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def _try_auto_discover_roles(data_dir: str) -> list:
    """Best-effort：对已配置 install_path 的实例跑 discover（失败写入 effects，不回滚配置）。"""
    effects = []
    try:
        from lib.composition import discover_roles_for_instance
        from lib.infra.utils import json_read

        cfg = json_read(os.path.join(data_dir, "config.json"), {})
        instances = cfg.get("agent_instances") or {}
        if not isinstance(instances, dict):
            return effects
        for iid, inst in instances.items():
            if not isinstance(inst, dict):
                continue
            if not (inst.get("install_path") or "").strip():
                effects.append({"op": "discover_roles", "instance_id": iid, "ok": False, "error": "missing_install_path"})
                continue
            try:
                roles = discover_roles_for_instance(inst)
                effects.append({
                    "op": "discover_roles",
                    "instance_id": iid,
                    "ok": True,
                    "roles": len(roles) if isinstance(roles, list) else 0,
                })
            except Exception as exc:
                effects.append({"op": "discover_roles", "instance_id": iid, "ok": False, "error": str(exc)})
    except Exception as exc:
        effects.append({"op": "discover_roles", "ok": False, "error": str(exc)})
    return effects


def handle_compose_files_list(handler):
    """GET /api/settings/compose-files — 列出可编辑 compose yml（无启停）。"""
    from lib.composition import list_compose_files
    from lib.infra.constants import MAILBUS_ROOT

    try:
        files = list_compose_files(MAILBUS_ROOT)
        handler._send_json({
            "status": "ok",
            "files": files,
            "note": "仅加载/编辑/保存 YAML；docker compose / k8s 启停由运维侧执行",
        })
    except Exception as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def handle_compose_file_get(handler, rel: str):
    from lib.composition import read_compose_file
    from lib.infra.constants import MAILBUS_ROOT

    try:
        handler._send_json({"status": "ok", **read_compose_file(MAILBUS_ROOT, rel)})
    except FileNotFoundError:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def handle_compose_file_put(handler, rel: str):
    from lib.composition import write_compose_file
    from lib.infra.constants import MAILBUS_ROOT

    body = handler._read_post_body() or {}
    content = body.get("content")
    if content is None:
        handler._send_json({"status": "error", "error": "content required"}, 400)
        return
    try:
        handler._send_json({"status": "ok", **write_compose_file(MAILBUS_ROOT, rel, str(content))})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def handle_settings_services_probe(handler):
    """POST /api/settings/section/services/probe — lightweight connectivity check."""
    # 跨层解耦：api→adapter 通过 composition 拿服务
    from lib.composition import probe_service

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
    handler._send_json({"status": "ok", **config_env_status(handler.data_dir)})


def handle_settings_env_patch(handler):
    body = handler._read_post_body()
    vars_patch = body.get("vars") or body
    if not isinstance(vars_patch, dict):
        handler._send_json({"status": "error", "error": "vars must be object"}, 400)
        return
    result = config_patch_env(handler.data_dir, vars_patch)
    handler._send_json({"status": "ok", **result})


def handle_integrations(handler):
    """GET/POST /api/settings/integrations — list adapters; POST add/remove plugin specs."""
    from lib.application.integrations_query import integrations_overview
    # 跨层解耦：api→adapter 通过 composition 拿服务
    from lib.composition import config_path
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
                # 跨层解耦：api→adapter 通过 composition 拿服务
                from lib.composition import reload_integration_plugins

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
