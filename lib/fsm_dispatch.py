"""FSM 步骤 inbox 推送 — API rollback 与 pipeline_trigger 共用。"""

from __future__ import annotations

import os

from .utils import json_read, resolve_paths


def dispatch_fsm_step(
    data_dir: str,
    task_id: str,
    step: dict,
    *,
    summary: str = "",
) -> bool:
    """将 FSM 步骤推送到 assignee inbox。成功返回 True。"""
    from .pipeline_trigger import _send_task
    from .transport.dispatch_integration import dispatch_pipeline_step, transport_router_enabled

    to_person = step.get("to_person") or step.get("to_agent") or ""
    if not to_person:
        return False

    config = json_read(os.path.join(data_dir, "config.json"), {})
    text = summary or step.get("rollback_reason") or ""
    if transport_router_enabled(config):
        agents_cfg = config.get("agents") or {}
        rt = step.get("role_type") or 0
        r = dispatch_pipeline_step(
            data_dir,
            task_id=task_id,
            step_id=step.get("step_id") or "",
            to_agent=to_person,
            role_type=int(rt),
            intent=text,
            agents=agents_cfg,
            config=config,
        )
        if not r.get("skipped"):
            return bool(r.get("ok"))

    paths = resolve_paths(data_dir)
    return _send_task(
        data_dir,
        paths,
        step.get("from_person", "mailbus"),
        step.get("from_role", ""),
        step.get("to_role", ""),
        to_person,
        text,
        task_id,
        step_num=step.get("step") or 1,
        step_id=step.get("step_id"),
        result_ref=step.get("result_ref"),
    )
