"""任务 assignee failover — 离线/僵尸时换派。"""

from __future__ import annotations

import os
from typing import Optional, Set

from ..dispatch.agent_availability import get_offline_agents, is_agent_offline
from ..dispatch.role_resolver import resolve_agent_for_role_type
from ..dispatch.tier_filter import dispatch_action_from_envelope
from ..pipeline_step import step_agent
from ..utils import json_read, json_write


def reassign_task_if_assignee_offline(
    data_dir: str,
    task: dict,
    *,
    exclude: Optional[Set[str]] = None,
) -> Optional[str]:
    """
    若 task assignee 离线，解析新 agent 并更新 chain 活跃步。
    返回新 assignee；无变更返回 None。
    """
    assignee = task.get("assignee") or ""
    if not assignee or not is_agent_offline(data_dir, assignee):
        return None

    chain = task.get("chain") or []
    if not chain:
        return None

    active = chain[-1]
    for step in reversed(chain):
        st = step.get("status") or step.get("fsm_state") or ""
        if st in ("running", "queued", "dispatched", "in_progress", "awaiting_result"):
            active = step
            break

    rt = active.get("role_type")
    if rt is None:
        return None

    skip = set(exclude or set())
    skip.add(assignee)
    action = dispatch_action_from_envelope(task)
    agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}
    new_agent, meta = resolve_agent_for_role_type(
        data_dir,
        int(rt),
        exclude=skip,
        pin_agent=active.get("pin_agent"),
        action=action,
        agents_cfg=agents_cfg,
    )
    if not new_agent or new_agent == assignee:
        return None

    meta = dict(meta or {})
    meta["failover_from"] = assignee
    active["to_agent"] = new_agent
    active["to_person"] = new_agent
    active["dispatch_meta"] = meta
    task["assignee"] = new_agent

    tid = task.get("task_id") or task.get("id") or ""
    if tid:
        json_write(os.path.join(data_dir, "tasks", f"{tid}.json"), task)
    return new_agent


def maybe_failover_running_tasks(data_dir: str, agents: dict) -> dict:
    """扫描 running 任务，离线 assignee 自动换派。返回 {task_id: new_agent}。"""
    offline = get_offline_agents(data_dir)
    if not offline:
        return {}

    tasks_dir = os.path.join(data_dir, "tasks")
    if not os.path.isdir(tasks_dir):
        return {}

    changed = {}
    for name in os.listdir(tasks_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(tasks_dir, name)
        task = json_read(path, {})
        if (task.get("status") or "") not in ("running", "pending"):
            fsm = task.get("fsm") or {}
            if fsm.get("state") not in ("executing", "created", "accepting", "blocked"):
                continue
        assignee = task.get("assignee") or step_agent((task.get("chain") or [{}])[-1])
        if assignee not in offline:
            continue
        new_agent = reassign_task_if_assignee_offline(data_dir, task, exclude={assignee})
        if new_agent:
            changed[task.get("task_id") or name[:-5]] = new_agent
    return changed
