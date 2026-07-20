"""取消在途 A2A Task（CancelTask RPC）。"""
from __future__ import annotations

import os
from typing import Any, Optional

from ..utils import json_read
from .a2a_standard import A2ATransport
from .types import DispatchContext


_INFLIGHT = frozenset({"queued", "running", "dispatched", "waiting", "working"})


def cancel_inflight_a2a_for_task(
    data_dir: str,
    task: dict,
    *,
    agents: Optional[dict] = None,
    reason: str = "",
) -> list[dict[str, Any]]:
    """对 chain 中在途 a2a_task_id 调用 CancelTask；返回每次 RPC 结果。"""
    cfg = json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else {}
    agents = agents or cfg.get("agents") or {}
    transport = A2ATransport(config=cfg, data_dir=data_dir)
    tid = task.get("task_id") or task.get("id") or ""
    outcomes: list[dict[str, Any]] = []
    for step in task.get("chain") or []:
        if not isinstance(step, dict):
            continue
        a2a_id = step.get("a2a_task_id")
        if not a2a_id:
            continue
        fs = (step.get("fsm_state") or step.get("status") or "").lower()
        if fs not in _INFLIGHT and step.get("status") in ("completed", "done", "skipped"):
            continue
        to_agent = step.get("to_agent") or step.get("to_person") or ""
        ctx = DispatchContext(
            data_dir=data_dir,
            task_id=tid,
            step_id=step.get("step_id") or "",
            to_agent=to_agent,
            role_type=int(step.get("role_type") or 0),
        )
        try:
            out = transport.cancel_task(ctx, a2a_id, agents)
            outcomes.append({"step_id": step.get("step_id"), "a2a_task_id": a2a_id, **out})
        except Exception as exc:
            outcomes.append({
                "step_id": step.get("step_id"),
                "a2a_task_id": a2a_id,
                "ok": False,
                "error": str(exc),
                "reason": reason,
            })
    return outcomes
