"""Pipeline step 字段 accessor — v3 (role_type/to_agent) 与 Legacy 双读。"""

from __future__ import annotations

from typing import List, Optional


def is_v3_task(task: dict) -> bool:
    if task.get("protocol_version", "").startswith("mailbus-a2a/"):
        return True
    chain = task.get("chain") or []
    if not chain:
        return False
    head = chain[0] if isinstance(chain[0], dict) else {}
    if head.get("role_type") is not None:
        return True
    if head.get("planned_role_types") is not None:
        return True
    if head.get("to_agent"):
        return True
    return False


def is_pipeline_step(item) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(item.get("to_agent") or item.get("to_person"))


def step_agent(step: dict) -> str:
    return step.get("to_agent") or step.get("to_person") or ""


def step_role_type(step: dict) -> Optional[int]:
    rt = step.get("role_type")
    if rt is not None:
        try:
            return int(rt)
        except (TypeError, ValueError):
            return None
    return None


def step_role_zh(step: dict) -> str:
    from .locale.role_labels import role_type_to_zh

    rt = step_role_type(step)
    if rt is not None:
        return role_type_to_zh(rt)
    return step.get("to_role") or ""


def planned_role_types_remaining(chain: List[dict]) -> List[int]:
    head = chain[0] if chain else {}
    planned = head.get("planned_role_types")
    if isinstance(planned, list):
        out = []
        for x in planned:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    return []


def planned_agents_remaining(chain: List[dict]) -> List[str]:
    """Legacy string 队列；v3 任务返回 []（请用 planned_role_types_remaining）。"""
    head = chain[0] if chain else {}
    if head.get("planned_role_types") is not None:
        return []
    planned = head.get("planned_agents")
    return list(planned) if isinstance(planned, list) else []


def agents_served(chain: List[dict]) -> set:
    return {step_agent(s) for s in chain if step_agent(s)}
