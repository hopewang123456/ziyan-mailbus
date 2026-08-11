"""can_deliver(a2a) 与 step 审计字段写入。"""
from __future__ import annotations

import os
from typing import Any, Optional

from lib.infra.utils import json_read, json_write, _now_iso
from .agent_card_cache import enrich_agent_channels
from .types import DispatchContext


def can_deliver_a2a(agent_id: str, agent_cfg: dict, ctx: DispatchContext) -> bool:
    agent_cfg = enrich_agent_channels(agent_id, dict(agent_cfg or {}))
    if ctx.force_transport == "file_bus":
        return False
    if (agent_cfg or {}).get("transport") == "local_cli":
        return False
    if (agent_cfg or {}).get("runtime") == "human":
        return False
    channels = (agent_cfg or {}).get("channels") or {}
    a2a_ch = channels.get("a2a") or {}
    if a2a_ch.get("enabled") is False:
        return False
    endpoint = (agent_cfg or {}).get("endpoint") or {}
    card = (agent_cfg or {}).get("agent_card") or (agent_cfg or {}).get("wire") or {}
    interfaces = (
        card.get("supportedInterfaces")
        or (agent_cfg or {}).get("supportedInterfaces")
        or []
    )
    if not interfaces and not endpoint.get("base_url") and not endpoint.get("rpc_url"):
        return False
    return True


def persist_step_transport(
    data_dir: str,
    ctx: DispatchContext,
    *,
    transport_used: str,
    transport_attempts: list[dict[str, Any]],
    a2a_task_id: Optional[str] = None,
    a2a_retries_exhausted: bool = False,
) -> None:
    """将 transport 审计写入 store/tasks/{task_id}.json 对应 step。"""
    task_path = os.path.join(data_dir, "tasks", f"{ctx.task_id}.json")
    if not os.path.isfile(task_path):
        return
    task = json_read(task_path, {})
    chain = task.get("chain") or []
    for step in chain:
        if not isinstance(step, dict):
            continue
        if step.get("step_id") == ctx.step_id:
            step["transport_used"] = transport_used
            step["transport_attempts"] = transport_attempts
            if a2a_task_id:
                step["a2a_task_id"] = a2a_task_id
            if a2a_retries_exhausted:
                step["a2a_retries_exhausted"] = True
            break
    task["updated_at"] = _now_iso()
    json_write(task_path, task)
