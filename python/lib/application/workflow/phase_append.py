"""Workflow phase 链追加 — fixed_phases / llm_adaptive。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def append_phase_steps(task: dict, phase: dict) -> List[int]:
    steps = phase.get("steps") or []
    rts: List[int] = []
    head = (task.get("chain") or [{}])[0]
    for step in steps:
        if step.get("node_type") == "agent":
            rt = int(step.get("role_type") or 0)
            if rt:
                rts.append(rt)
    if rts:
        head["planned_role_types"] = list(rts) + list(head.get("planned_role_types") or [])
    return rts


def append_single_role_type(task: dict, role_type: int, *, pin_agent: str = "") -> None:
    head = (task.get("chain") or [{}])[0]
    planned = list(head.get("planned_role_types") or [])
    planned.insert(0, int(role_type))
    head["planned_role_types"] = planned
    if pin_agent:
        head["pin_agent"] = pin_agent


def spawn_phase_chain(task: dict, phase: dict, *, data_dir: str = "") -> None:
    append_phase_steps(task, phase)
