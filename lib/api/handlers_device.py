"""mailbus HTTP API — Device Bridge 路由处理器。

处理: POST /api/device/chat（通讯式一轮一答）、GET /api/device/chat/<ticket_id>（超时取票）。
鉴权独立于 mailbus API token：设备 token（Authorization Bearer / X-Mailbus-Device-Token）。
"""
from __future__ import annotations

from lib.application.device_bridge import (
    DeviceBridgeError,
    deliver_and_wait,
    load_bridge_config,
    resolve_device,
    resolve_ticket,
    set_memory_recorder,
)


def _write_device_memory(data_dir, agent_id, device_id, text, msg_id, role) -> None:
    """实际记忆落盘：SQLite 同步 + AgentMemory 后台线程降级，均不抛异常。"""
    import threading

    from lib.adapters.integrations import memory_bridge as mb

    from_agent = f"device:{device_id}" if role == "user" else agent_id
    key_id = msg_id if role == "user" else f"{msg_id}-assistant"

    if mb.bridge_sqlite_enabled():
        try:
            mb.write_memory_to_sqlite(agent_id, key_id, text, from_agent, "notice")
        except Exception:
            pass

    if mb.bridge_agentmemory_enabled():
        def _am_write():
            try:
                if mb.agentmemory_healthy():
                    mb.write_memory_to_agentmemory(agent_id, key_id, text, from_agent, "notice")
            except Exception:
                pass

        threading.Thread(target=_am_write, daemon=True).start()


set_memory_recorder(_write_device_memory)


def _presented_token(handler) -> str:
    auth = (handler.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (handler.headers.get("X-Mailbus-Device-Token") or "").strip()


def _client_ip(handler) -> str:
    try:
        return str(handler.client_address[0] or "")
    except Exception:
        return ""


def _resolve_authenticated_device(handler) -> dict:
    bridge_cfg = load_bridge_config(handler.data_dir)
    if not bridge_cfg.get("enabled", True):
        raise DeviceBridgeError("bridge_disabled", 403, "设备桥未启用")
    device = resolve_device(bridge_cfg, _presented_token(handler), _client_ip(handler))
    if not device:
        raise DeviceBridgeError("unauthorized", 401, "设备 token 无效或 IP 不在白名单")
    return device


def _live_agents(handler) -> dict:
    """每次从 config.json 读花名册，避免 UI 新增 agent 后须整进程重启才生效。"""
    from lib.infra.utils import json_read

    cfg = json_read(f"{handler.data_dir}/config.json", {})
    live = cfg.get("agents") if isinstance(cfg.get("agents"), dict) else None
    if live:
        # 同步到 handler，减少其它路径读到陈旧花名册
        try:
            handler.agents = live
        except Exception:
            pass
        return live
    return getattr(handler, "agents", None) or {}


def _live_agent_types(handler) -> dict:
    return getattr(handler, "agent_types", None) or {}


def handle_device_chat(handler):
    try:
        device = _resolve_authenticated_device(handler)
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    body = handler._read_post_body()
    if not isinstance(body, dict):
        body = {}
    action = str(body.get("action") or "chat").strip().lower()
    if action != "chat":
        handler._send_api_error(
            "unsupported_action", 400,
            detail=f"不支持的 action: {action!r}（MVP 仅 chat；建工单属 Phase 2）",
        )
        return

    text = str(body.get("text") or "").strip()
    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        import uuid

        session_id = uuid.uuid4().hex
    source = body.get("source") if isinstance(body.get("source"), dict) else {}

    bridge_cfg = load_bridge_config(handler.data_dir)
    wait_ms = int(bridge_cfg.get("default_wait_ms") or 45000)

    try:
        result = deliver_and_wait(
            handler.data_dir,
            _live_agents(handler),
            _live_agent_types(handler),
            device,
            text,
            session_id,
            wait_ms,
            source,
        )
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    handler._send_json(result)


def handle_device_ticket(handler, ticket_id: str):
    try:
        device = _resolve_authenticated_device(handler)
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    try:
        result = resolve_ticket(handler.data_dir, ticket_id)
    except DeviceBridgeError as exc:
        handler._send_api_error(exc.code, exc.status, detail=exc.detail)
        return

    handler._send_json(result)
