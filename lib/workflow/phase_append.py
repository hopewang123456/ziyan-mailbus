"""Phase steps → planned_role_types / chain 重建。"""

from __future__ import annotations

from typing import List

from ..dispatch.role_resolver import resolve_agent_for_role_type
from ..pipeline_chain import init_chain_from_planned


def agent_role_types(phase: dict) -> List[int]:
    out = []
    for s in phase.get("steps") or []:
        if s.get("node_type") == "agent" and s.get("role_type") is not None:
            out.append(int(s["role_type"]))
    return out


def append_phase_steps(task: dict, phase: dict) -> List[int]:
    """append_phase：追加 phase agent steps 到 head.planned_role_types。"""
    chain = task.get("chain") or []
    if not chain:
        return []
    head = chain[0]
    rts = agent_role_types(phase)
    planned = list(head.get("planned_role_types") or [])
    head["planned_role_types"] = planned + rts
    return rts


def spawn_phase_chain(task: dict, phase: dict, *, data_dir: str) -> bool:
    """spawn_phase：用 phase steps 重建 chain[0]。"""
    rts = agent_role_types(phase)
    if not rts:
        return False
    task_id = task.get("task_id") or task.get("id") or ""
    planned = [{"role_type": rt} for rt in rts]
    task["chain"] = init_chain_from_planned(
        planned,
        task_id,
        resolve_agent=lambda rt, pin: resolve_agent_for_role_type(
            data_dir, rt, pin_agent=pin,
        ),
    )
    task["assignee"] = task["chain"][0].get("to_agent") or ""
    return True


def append_single_role_type(task: dict, role_type: int, *, pin_agent: str = "") -> None:
    chain = task.get("chain") or []
    if not chain:
        return
    head = chain[0]
    planned = list(head.get("planned_role_types") or [])
    planned.append(int(role_type))
    head["planned_role_types"] = planned
    if pin_agent:
        head.setdefault("pin_agent", pin_agent)
