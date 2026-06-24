"""pipeline 下一步角色/执行人解析 — v3 role_type + Legacy 兼容。"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from .pipeline_chain import AGENT_ROLE, agent_to_role
from .pipeline_step import (
    agents_served,
    planned_agents_remaining,
    planned_role_types_remaining,
    step_agent,
    step_role_type,
)
from .role_flow import (
    get_next_role,
    get_next_role_type,
    is_terminal_role_type,
    pick_agent_for_role_type,
    pick_person_for_role,
)

VALID_ROLES = frozenset({
    "方案设计师", "调度员", "开发工程师", "审查官", "测试工程师", "验收员",
    "安全审计师", "技术研究员", "巡检官", "运营", "市场拓展官", "财务跟进官",
})

TERMINAL_CONCLUSIONS = frozenset({
    ("验收员", "approved"),
    ("验收员", "rejected"),
    ("运营", "done"),
    ("巡检官", "done"),
    ("调度员", "approved"),
})


def _known_agent_ids(agents: Optional[dict]) -> Set[str]:
    if agents:
        return set(agents.keys())
    return set(AGENT_ROLE.keys())


def _pick_explicit_person(result: dict, known: Set[str]) -> Optional[str]:
    cand = result.get("next_person") or result.get("next_agent")
    if isinstance(cand, str) and cand in known:
        return cand
    nxt = result.get("next")
    if isinstance(nxt, str) and nxt in known and nxt not in VALID_ROLES:
        return nxt
    return None


def is_pipeline_terminal(
    current_role: str,
    conclusion: str,
    chain: List[dict],
    *,
    data_dir: str = "",
    current_role_type: Optional[int] = None,
) -> bool:
    if planned_role_types_remaining(chain) or planned_agents_remaining(chain):
        return False
    if current_role_type is not None and data_dir:
        return is_terminal_role_type(current_role_type, conclusion, data_dir)
    return (current_role, (conclusion or "").lower()) in {
        (r, c.lower()) for r, c in TERMINAL_CONCLUSIONS
    }


def resolve_next_assignee_v3(
    chain: List[dict],
    result: dict,
    current_role_type: int,
    conclusion: str,
    data_dir: str,
    agents: Optional[dict] = None,
    task: Optional[dict] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """v3：返回 (next_role_type, next_agent)。"""
    from .dispatch.tier_filter import dispatch_action_from_envelope

    known = _known_agent_ids(agents)
    head = chain[0] if chain else {}
    planned = planned_role_types_remaining(chain)
    task_action = dispatch_action_from_envelope(task or {})

    if planned:
        while planned:
            n_rt = planned.pop(0)
            head["planned_role_types"] = planned
            n_agent = pick_agent_for_role_type(
                data_dir, n_rt, exclude=agents_served(chain), action=task_action,
            )
            cur = step_agent(chain[-1]) if chain else ""
            if n_agent and n_agent != cur:
                return n_rt, n_agent
        # planned 耗尽 → role_flow

    hint_rt = result.get("next_role_type")
    if hint_rt is not None:
        try:
            n_rt = int(hint_rt)
        except (TypeError, ValueError):
            n_rt = get_next_role_type(current_role_type, conclusion, data_dir)
    else:
        n_rt = get_next_role_type(current_role_type, conclusion, data_dir)

    if n_rt is None:
        return None, None

    explicit = _pick_explicit_person(result, known)
    if explicit:
        return n_rt, explicit

    n_agent = pick_agent_for_role_type(
        data_dir, n_rt, exclude=agents_served(chain), action=task_action,
    )
    return n_rt, n_agent


def resolve_next_assignee(
    chain: List[dict],
    result: dict,
    current_role: str,
    conclusion: str,
    agents: Optional[dict] = None,
    *,
    data_dir: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """
    Legacy 签名：(next_role_zh, next_person)。
    v3 chain 时内部走 role_type 路径，返回中文 role + agent。
    """
    head = chain[0] if chain else {}
    crt = step_role_type(chain[-1]) if chain else None
    if crt is not None and (head.get("planned_role_types") is not None or chain[-1].get("to_agent")):
        if not data_dir:
            data_dir = _default_data_dir()
        n_rt, n_agent = resolve_next_assignee_v3(
            chain, result, crt, conclusion, data_dir, agents,
        )
        if n_rt is None:
            return None, None
        from .locale.role_labels import role_type_to_zh
        return role_type_to_zh(n_rt, data_dir), n_agent

    known = _known_agent_ids(agents)
    planned = head.get("planned_agents")

    if isinstance(planned, list) and planned:
        while planned:
            n_person = planned.pop(0)
            head["planned_agents"] = planned
            cur_person = step_agent(chain[-1]) if chain else ""
            if n_person and n_person != cur_person:
                return agent_to_role(n_person) or "方案设计师", n_person

    explicit_person = _pick_explicit_person(result, known)
    explicit_next = result.get("next_role")
    if explicit_next and explicit_next != current_role:
        n_role = explicit_next
    else:
        n_role = get_next_role(current_role, conclusion)

    if not n_role:
        return None, None

    if explicit_person:
        return agent_to_role(explicit_person) or n_role, explicit_person

    served = {step_agent(s) for s in chain if step_agent(s)}
    n_person = pick_person_for_role(n_role, exclude=served)
    return n_role, n_person


def _default_data_dir() -> str:
    import os
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "store",
    )
