"""Transport Router 工厂与 pipeline 派发接线。"""
from __future__ import annotations

import os
from typing import Any, Optional

from lib.application.harness import get_harness
from lib.infra.utils import json_read
from .agent_card_cache import enrich_agent_channels
from .file_bus import FileBusTransport
from .router import TransportRouter
from .types import DispatchContext


def transport_router_enabled(config: Optional[dict] = None) -> bool:
    cfg = config or {}
    return bool((cfg.get("transport") or {}).get("use_router"))


def merge_agent_transport_config(agents: dict) -> dict:
    """合并 agent-channels 默认；agent 可设 channels.a2a.use_streaming 覆盖全局 transport.a2a.use_streaming。"""
    out = {}
    for aid, acfg in (agents or {}).items():
        out[aid] = enrich_agent_channels(aid, dict(acfg or {}))
    return out


def build_router(data_dir: str, config: Optional[dict] = None) -> TransportRouter:
    cfg = config or json_read(os.path.join(data_dir, "config.json"), {})
    harness = get_harness(cfg)
    mode = (cfg.get("harness") or {}).get("mode", "production")
    return TransportRouter(
        data_dir=data_dir,
        config=cfg,
        file_bus=FileBusTransport(harness=harness, mode=mode),
    )


def context_from_pipeline_step(
    data_dir: str,
    *,
    task_id: str,
    step_id: str,
    to_agent: str,
    role_type: int,
    intent: str = "",
    msg_file: Optional[str] = None,
) -> DispatchContext:
    return DispatchContext(
        data_dir=data_dir,
        task_id=task_id,
        step_id=step_id,
        to_agent=to_agent,
        role_type=role_type,
        intent=intent,
        msg_file=msg_file,
    )


def send_via_message_port(
    data_dir: str,
    *,
    to_agent: str,
    msg_id: str,
    intent: str = "",
    channel: str = "",
    task_id: str = "",
    step_id: str = "",
    role_type: int = 0,
    wait: bool = False,
    allow_no_spawn: bool = False,
    wait_timeout_sec: int | None = None,
    config: Optional[dict] = None,
) -> dict[str, Any]:
    """Wave3/W7c: MessageTransportPort 统一发送（可选 Harness wait）。"""
    from lib.application.transport_send import send_outbound

    return send_outbound(
        data_dir,
        agent_id=to_agent,
        msg_id=msg_id,
        intent=intent,
        channel=channel,
        task_id=task_id,
        step_id=step_id,
        role_type=role_type,
        wait=wait,
        allow_no_spawn=allow_no_spawn,
        wait_timeout_sec=wait_timeout_sec,
        config=config,
    )


def dispatch_pipeline_step(
    data_dir: str,
    *,
    task_id: str,
    step_id: str,
    to_agent: str,
    role_type: int,
    intent: str,
    agents: Optional[dict] = None,
    config: Optional[dict] = None,
) -> dict[str, Any]:
    """pipeline 派发：启用 use_router 时走 TransportRouter，否则返回 skipped。

    W7c：`transport.use_message_port` 为真时，file_bus 厚路径（含 wait）走 MessageTransportPort。
    """
    cfg = config or json_read(os.path.join(data_dir, "config.json"), {})
    if not transport_router_enabled(cfg):
        return {"skipped": True, "reason": "use_router_disabled"}

    tcfg = cfg.get("transport") or {}
    if tcfg.get("use_message_port"):
        return _dispatch_via_message_port(
            data_dir,
            task_id=task_id,
            step_id=step_id,
            to_agent=to_agent,
            role_type=role_type,
            intent=intent,
            config=cfg,
        )

    agents = merge_agent_transport_config(agents or cfg.get("agents") or {})
    router = build_router(data_dir, cfg)
    ctx = context_from_pipeline_step(
        data_dir,
        task_id=task_id,
        step_id=step_id,
        to_agent=to_agent,
        role_type=role_type,
        intent=intent,
    )
    result = router.dispatch_step(ctx, agents)
    out: dict[str, Any] = {
        "ok": result.ok or result.awaiting_human,
        "transport_used": result.transport_used,
        "a2a_task_id": result.a2a_task_id,
        "a2a_retries_exhausted": result.a2a_retries_exhausted,
        "awaiting_human": result.awaiting_human,
    }
    if result.step_result_path:
        out["step_result_path"] = result.step_result_path
    if result.error:
        out["error"] = result.error
        err = str(result.error)
        if err.startswith("retryable:"):
            out["error_code"] = "transport_retryable"
        elif "http_" in err:
            out["error_code"] = "transport_http"
        else:
            out["error_code"] = "delivery_failed"
        try:
            from lib.adapters.locale.errors_zh import message_zh

            out["message_zh"] = message_zh(out["error_code"], err)
        except Exception:
            pass
    if result.awaiting_human and result.human_queue_payload:
        from lib.adapters.orchestration.human_queue import enqueue

        hq = dict(result.human_queue_payload)
        hq.setdefault("task_id", task_id)
        hq_id = enqueue(data_dir, hq)
        out["human_queue_id"] = hq_id
    return out


def _dispatch_via_message_port(
    data_dir: str,
    *,
    task_id: str,
    step_id: str,
    to_agent: str,
    role_type: int,
    intent: str,
    config: dict,
) -> dict[str, Any]:
    """W7c：调度经 MessageTransportPort（默认 file_bus + wait）。"""
    msg_id = f"msg-{task_id}-{step_id}"
    timeout = int(
        ((config.get("harness") or {}).get("file_bus") or {}).get("ack_timeout_sec")
        or config.get("ack_timeout")
        or 300
    )
    receipt = send_via_message_port(
        data_dir,
        to_agent=to_agent,
        msg_id=msg_id,
        intent=intent,
        channel="file_bus",
        task_id=task_id,
        step_id=step_id,
        role_type=role_type,
        wait=True,
        allow_no_spawn=True,
        wait_timeout_sec=timeout,
        config=config,
    )
    out: dict[str, Any] = {
        "ok": bool(receipt.get("ok")),
        "transport_used": receipt.get("channel") or "file_bus",
        "msg_id": receipt.get("msg_id") or msg_id,
        "detail": receipt.get("detail") or "",
        "via": "message_transport_port",
    }
    if not out["ok"]:
        out["error"] = receipt.get("detail") or "transport_failed"
        out["error_code"] = receipt.get("error_code") or "delivery_failed"
        if receipt.get("message_zh"):
            out["message_zh"] = receipt["message_zh"]
    else:
        from lib.application.orchestration.pipeline.results import step_result_path

        path = step_result_path(data_dir, task_id, step_id)
        if os.path.isfile(path):
            out["step_result_path"] = path
    return out
