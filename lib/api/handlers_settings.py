"""GET/POST /api/settings/* — Dashboard 配置中心。"""

from __future__ import annotations

from lib.config_admin import (
    env_status,
    get_section,
    list_sections,
    patch_env,
    patch_section,
)


def handle_settings_sections(handler):
    handler._send_json({"status": "ok", "sections": list_sections()})


def handle_settings_section_get(handler, section: str):
    try:
        handler._send_json({"status": "ok", **get_section(handler.data_dir, section)})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


def handle_settings_section_patch(handler, section: str):
    body = handler._read_post_body()
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
    try:
        result, _restart = patch_section(handler.data_dir, section, patch)
        handler._send_json({"status": "ok", **result})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)


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
