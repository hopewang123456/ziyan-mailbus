"""Pipeline step 字段访问与 planned 队列 — role-pipeline chain 辅助。"""
from __future__ import annotations

from typing import Any, List

_ROLE_TYPE_ZH = {
    1: "方案设计师",
    2: "安全审计师",
    3: "技术研究员",
    4: "市场拓展官",
    5: "审查官",
    6: "测试工程师",
    7: "巡检官",
    8: "开发工程师",
    9: "调度员",
    10: "财务跟进官",
    11: "运营",
    12: "验收员",
}

_AGENT_ROLE = {
    "lingzhao": "方案设计师",
    "xiaoqi": "调度员",
    "lingxiao": "开发工程师",
    "dali": "开发工程师",
    "lingjian": "审查官",
    "lingyun": "开发工程师",
    "lingyan": "测试工程师",
    "lingjin": "安全审计师",
    "lingxi": "技术研究员",
    "lingxun": "巡检官",
    "lingtuo": "市场拓展官",
    "lingzhang": "财务跟进官",
    "yige": "运营",
}


def is_pipeline_step(item: Any) -> bool:
    return isinstance(item, dict) and bool(item.get("step_id") or item.get("to_agent") or item.get("to_person"))


def is_role_pipeline_task(task: dict) -> bool:
    """True when chain head carries role_type / planned_role_types (current pipeline schema)."""
    chain = task.get("chain") or []
    if not chain or not isinstance(chain[0], dict):
        return False
    head = chain[0]
    return bool(head.get("planned_role_types") is not None or head.get("role_type") is not None)



def step_agent(step: dict) -> str:
    return (step.get("to_agent") or step.get("to_person") or "").strip()


def step_role_type(step: dict) -> int:
    rt = step.get("role_type")
    if rt is not None:
        return int(rt)
    role = step.get("to_role") or ""
    for k, zh in _ROLE_TYPE_ZH.items():
        if zh == role:
            return k
    return 0


def step_role_zh(step: dict) -> str:
    role = step.get("to_role")
    if role:
        return role
    rt = step.get("role_type")
    if rt is not None:
        return _ROLE_TYPE_ZH.get(int(rt), "方案设计师")
    agent = step_agent(step)
    return _AGENT_ROLE.get(agent, "方案设计师") if agent else "方案设计师"


def planned_agents_remaining(chain: List[dict]) -> List[str]:
    head = chain[0] if chain else {}
    planned = head.get("planned_agents")
    return list(planned) if isinstance(planned, list) else []


def planned_role_types_remaining(chain: List[dict]) -> List[int]:
    head = chain[0] if chain else {}
    planned = head.get("planned_role_types")
    if isinstance(planned, list):
        return [int(x) for x in planned]
    return []


__all__ = [
    "is_pipeline_step",
    "is_role_pipeline_task",
    "step_agent",
    "step_role_type",
    "step_role_zh",
    "planned_agents_remaining",
    "planned_role_types_remaining",
]
