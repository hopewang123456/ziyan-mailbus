"""角色流转规则 — role-flow.json SoT + Legacy 中文兼容。"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional, Set

from .utils import json_read

# Legacy 硬编码（fallback）
_FLOW_RULES = {
    ("开发工程师", "done"): "审查官",
    ("开发工程师", "blocked"): "方案设计师",
    ("审查官", "pass"): "测试工程师",
    ("审查官", "fail"): "开发工程师",
    ("测试工程师", "pass"): "验收员",
    ("测试工程师", "fail"): "开发工程师",
    ("验收员", "approved"): None,
    ("验收员", "rejected"): "开发工程师",
    ("调度员", "dispatched"): "开发工程师",
    ("调度员", "approved"): None,
    ("方案设计师", "approved"): "调度员",
    ("方案设计师", "done"): "调度员",
    ("方案设计师", "need_research"): "技术研究员",
    ("安全审计师", "pass"): "审查官",
    ("安全审计师", "fail"): "开发工程师",
    ("技术研究员", "done"): "方案设计师",
    ("巡检官", "done"): None,
    ("巡检官", "warning"): "方案设计师",
    ("运营", "done"): None,
    ("市场拓展官", "pursue"): "方案设计师",
    ("市场拓展官", "handed_to_lingzhao"): "方案设计师",
    ("市场拓展官", "watch"): None,
    ("市场拓展官", "reject"): None,
}

_ROLE_MAP = {
    "方案设计师": ["lingzhao"],
    "调度员": ["xiaoqi"],
    "开发工程师": ["lingxiao", "dali", "lingyun"],
    "审查官": ["lingjian"],
    "测试工程师": ["lingyan"],
    "安全审计师": ["lingjin"],
    "技术研究员": ["lingxi"],
    "巡检官": ["lingxun"],
    "市场拓展官": ["lingtuo"],
    "财务跟进官": ["lingzhang"],
    "运营": ["yige"],
    "验收员": ["xiaoqi"],
}


@lru_cache(maxsize=4)
def _load_role_flow_cached(path: str) -> dict:
    return json_read(path, {})


def load_role_flow(data_dir: str) -> dict:
    path = os.path.join(data_dir, "roles", "json", "role-flow.json")
    return _load_role_flow_cached(path)


def get_next_role_type(role_type: int, conclusion: str, data_dir: str) -> Optional[int]:
    flow = load_role_flow(data_dir)
    c = (conclusion or "").lower()
    for t in flow.get("transitions") or []:
        if int(t.get("from_role_type", -1)) == int(role_type) and (t.get("conclusion") or "").lower() == c:
            nxt = t.get("to_role_type")
            return int(nxt) if nxt is not None else None
    return None


def is_terminal_role_type(role_type: int, conclusion: str, data_dir: str) -> bool:
    flow = load_role_flow(data_dir)
    c = (conclusion or "").lower()
    for t in flow.get("terminal") or []:
        if int(t.get("role_type", -1)) == int(role_type) and (t.get("conclusion") or "").lower() == c:
            return True
    return False


def get_next_role(current_role: str, conclusion: str):
    return _FLOW_RULES.get((current_role, conclusion))


def pick_person_for_role(role: str, exclude=None):
    candidates = _ROLE_MAP.get(role, [])
    skip = exclude or set()
    for c in candidates:
        if c not in skip:
            return c
    return candidates[0] if candidates else None


def pick_agent_for_role_type(
    data_dir: str,
    role_type: int,
    exclude: Optional[Set[str]] = None,
    pin_agent: Optional[str] = None,
    action: Optional[dict] = None,
) -> Optional[str]:
    from .dispatch.role_resolver import resolve_agent_for_role_type

    step_action = action or {}
    agent, _ = resolve_agent_for_role_type(
        data_dir, int(role_type), exclude=exclude, pin_agent=pin_agent,
        action=step_action,
    )
    return agent


def get_online_status():
    return {role: persons for role, persons in _ROLE_MAP.items()}

