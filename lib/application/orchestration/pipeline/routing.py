"""pipeline 下一步角色/执行人解析 — planned_agents / next_person / role_flow。"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from lib.application.orchestration.pipeline.chain import AGENT_ROLE, agent_to_role
from lib.role_flow import get_next_role, pick_person_for_role

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


def planned_agents_remaining(chain: List[dict]) -> List[str]:
    head = chain[0] if chain else {}
    planned = head.get("planned_agents")
    return list(planned) if isinstance(planned, list) else []


def is_pipeline_terminal(
    current_role: str,
    conclusion: str,
    chain: List[dict],
    *,
    data_dir: str = "",
    current_role_type: Optional[int] = None,
) -> bool:
    """planned 未清空时永不终态；否则仅允许白名单 conclusion。"""
    from lib.application.orchestration.pipeline.step import planned_role_types_remaining

    if planned_agents_remaining(chain) or planned_role_types_remaining(chain):
        return False
    return (current_role, (conclusion or "").lower()) in {
        (r, c.lower()) for r, c in TERMINAL_CONCLUSIONS
    }


def _known_agent_ids(agents: Optional[dict]) -> Set[str]:
    if agents:
        return set(agents.keys())
    return set(AGENT_ROLE.keys())


def _persons_served(chain: List[dict]) -> Set[str]:
    return {s.get("to_person") for s in chain if s.get("to_person")}


def _pick_explicit_person(result: dict, known: Set[str]) -> Optional[str]:
    cand = result.get("next_person")
    if isinstance(cand, str) and cand in known:
        return cand
    nxt = result.get("next")
    if isinstance(nxt, str) and nxt in known and nxt not in VALID_ROLES:
        return nxt
    return None


def _resolve_role_type_assignee(
    chain: List[dict],
    role_type: int,
    *,
    data_dir: str,
    agents: Optional[dict],
) -> Tuple[Optional[str], Optional[str]]:
    from lib.locale.role_labels import role_type_to_zh

    head = chain[0] if chain else {}
    n_role = role_type_to_zh(int(role_type), data_dir)
    pin = head.get("pin_agent")
    if pin:
        # 首步 pin 不应劫持后续步骤：仅当 pin 是该 role_type 候选时沿用
        from lib.locale.role_labels import role_type_candidates

        cands = role_type_candidates(int(role_type), data_dir)
        if not cands or pin in cands:
            return n_role, pin
    n_person = pick_person_for_role(n_role, exclude=_persons_served(chain))
    return n_role, n_person


def resolve_next_assignee(
    chain: List[dict],
    result: dict,
    current_role: str,
    conclusion: str,
    agents: Optional[dict] = None,
    *,
    data_dir: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """解析 pipeline 下一步 (role, person)。"""
    from lib.application.orchestration.pipeline.step import planned_role_types_remaining

    known = _known_agent_ids(agents)
    head = chain[0] if chain else {}

    prt = planned_role_types_remaining(chain)
    if prt and data_dir:
        rt = int(prt[0])
        head["planned_role_types"] = prt[1:]
        return _resolve_role_type_assignee(chain, rt, data_dir=data_dir, agents=agents)

    planned = head.get("planned_agents")
    if isinstance(planned, list) and planned:
        while planned:
            n_person = planned.pop(0)
            head["planned_agents"] = planned
            cur_person = (chain[-1] or {}).get("to_person") if chain else ""
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

    n_person = pick_person_for_role(n_role, exclude=_persons_served(chain))
    return n_role, n_person
