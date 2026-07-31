"""API: discovery, framework/role enable, chain budget, align."""
from __future__ import annotations

from lib.application.align_store import align_store_from_registry
from lib.application.chain_route import apply_ollama_decision, ensure_llm_or_prompt, load_budget
from lib.application.discover_agents import save_report
from lib.application.lifecycle import (
    disable_framework,
    enable_framework,
    set_role_enabled,
)
from lib.application.queries import active_agents
from lib.locale.errors_zh import message_zh
from lib.utils import json_read


def handle_discover(handler):
    report = save_report(handler.data_dir)
    handler._send_json({"status": "ok", **report})


def handle_align(handler):
    body = {}
    try:
        body = handler._read_post_body() or {}
    except Exception:
        body = {}
    expect = int(body.get("expect_min") or 13)
    result = align_store_from_registry(handler.data_dir, expect_min=expect)
    status = "ok" if result.get("ok") else "warn"
    handler._send_json({"status": status, **result})


def handle_active_agents(handler):
    active = active_agents(handler.data_dir)
    handler._send_json({
        "status": "ok",
        "agents": [
            {"id": k, **{kk: vv for kk, vv in v.items() if kk != "push"}}
            for k, v in active.items()
        ],
    })


def handle_framework_enable(handler, framework_id: str):
    body = handler._read_post_body() or {}
    result = enable_framework(
        handler.data_dir,
        framework_id,
        mount_mode=str(body.get("mount_mode") or "container"),
        root_path=str(body.get("root_path") or ""),
        health_url=str(body.get("health_url") or ""),
        start_cmd=body.get("start_cmd"),
    )
    code = 200 if result.get("ok") else 400
    if result.get("error_code") and not result.get("ok"):
        result = {**result, "message_zh": message_zh(str(result["error_code"]), str(result.get("error") or ""))}
    handler._send_json({"status": "ok" if result.get("ok") else "error", **result}, code)


def handle_framework_disable(handler, framework_id: str):
    body = handler._read_post_body() or {}
    result = disable_framework(
        handler.data_dir,
        framework_id,
        confirm_fail_tasks=bool(body.get("confirm")),
        stop_cmd=body.get("stop_cmd"),
    )
    code = 200 if result.get("ok") else (409 if result.get("needs_confirm") else 400)
    if result.get("error_code") and not result.get("ok"):
        result = {**result, "message_zh": message_zh(str(result["error_code"]), str(result.get("error") or result.get("message") or ""))}
    handler._send_json({"status": "ok" if result.get("ok") else "error", **result}, code)


def handle_role_enable(handler, agent_id: str):
    body = handler._read_post_body() or {}
    enabled = body.get("enabled")
    if enabled is None:
        enabled = True
    result = set_role_enabled(handler.data_dir, agent_id, bool(enabled))
    code = 200 if result.get("ok") else 400
    if result.get("error_code") and not result.get("ok"):
        result = {**result, "message_zh": message_zh(str(result["error_code"]), str(result.get("error") or ""))}
    handler._send_json({"status": "ok" if result.get("ok") else "error", **result}, code)


def handle_chain_budget(handler):
    cfg = json_read(f"{handler.data_dir}/config.json", {})
    if handler.command == "POST":
        body = handler._read_post_body() or {}
        if "use_ollama" in body:
            use = body.get("use_ollama")
            if use is None or use == "null":
                use = None
            state = apply_ollama_decision(handler.data_dir, cfg, use_ollama=use)
            handler._send_json({"status": "ok", "budget": state})
            return
    state = load_budget(handler.data_dir, cfg)
    llm = ensure_llm_or_prompt(cfg)
    handler._send_json({"status": "ok", "budget": state, "llm": llm})


def handle_mailbus_token(handler):
    """GET: ensure + masked status. POST rotate: returns plaintext once."""
    from lib.application.mailbus_token import (
        client_context_from_handler,
        ensure_token,
        resolve_token,
        rotate_token,
    )
    from lib.locale.errors_zh import message_zh

    ctx = client_context_from_handler(handler)
    if handler.command == "POST":
        result = rotate_token(handler.data_dir, ctx)
        if not result.get("ok"):
            handler._send_json({
                "status": "error",
                **result,
                "message_zh": message_zh(str(result.get("error_code") or "unauthorized")),
            }, 401)
            return
        # refresh handler class token for subsequent requests in-process
        try:
            from lib.api.base import MailbusAPIHandler

            MailbusAPIHandler.auth_token = result.get("token")
        except Exception:
            pass
        handler._send_json({"status": "ok", "token": result["token"], "message": "rotated_once"})
        return

    tok = ensure_token(handler.data_dir)
    masked = (tok[:4] + "…" + tok[-4:]) if tok and len(tok) > 8 else "***"
    handler._send_json({
        "status": "ok",
        "configured": bool(resolve_token(handler.data_dir)),
        "token_masked": masked,
        "hint": "跨机写操作使用 Authorization: Bearer <token>；本机可免 token",
    })
