"""FSM 步骤 inbox 推送 — API rollback 与 pipeline_trigger 共用。"""

from __future__ import annotations

from typing import Optional

from .pipeline_step import step_agent, step_role_zh
from .utils import resolve_paths


def dispatch_fsm_step(
    data_dir: str,
    task_id: str,
    step: dict,
    *,
    summary: str = "",
) -> bool:
    """将 FSM 步骤推送到 assignee inbox。成功返回 True。"""
    from .pipeline_trigger import _send_task

    to_agent = step_agent(step)
    if not to_agent:
        return False

    paths = resolve_paths(data_dir)
    text = summary or step.get("rollback_reason") or ""
    to_role = step.get("to_role") or step_role_zh(step)
    from_agent = step.get("from_agent") or step.get("from_person", "mailbus")
    from_role = step.get("from_role") or ""
    return _send_task(
        data_dir,
        paths,
        from_agent,
        from_role,
        to_role,
        to_agent,
        text,
        task_id,
        step_num=step.get("step") or 1,
        step_id=step.get("step_id"),
        result_ref=step.get("result_ref"),
    )
