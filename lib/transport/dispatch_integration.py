"""Transport Router 工厂与 pipeline 派发接线。"""
from __future__ import annotations

import os
from typing import Any, Optional

from ..harness import get_harness
from ..utils import json_read
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
    """pipeline 派发：启用 use_router 时走 TransportRouter，否则返回 skipped。"""
    cfg = config or json_read(os.path.join(data_dir, "config.json"), {})
    if not transport_router_enabled(cfg):
        return {"skipped": True, "reason": "use_router_disabled"}
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
    if result.awaiting_human and result.human_queue_payload:
        from ..human_queue import enqueue

        hq = dict(result.human_queue_payload)
        hq.setdefault("task_id", task_id)
        hq_id = enqueue(data_dir, hq)
        out["human_queue_id"] = hq_id
    return out
