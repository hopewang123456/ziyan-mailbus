"""角色流转规则 — role-flow.json SoT + Legacy 中文兼容。"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional, Set

from lib.infra.agent_demo import pipeline_role_flow
from lib.infra.utils import json_read

# Legacy 硬编码（fallback，仅当 JSON SoT 缺失时使用通用 demo 名）
_FLOW_RULES = {
    tuple(k.split("|", 1)): v for k, v in (pipeline_role_flow() or {}).items()
}
# 兼容空串表示终止
_FLOW_RULES = {k: (v or None) for k, v in _FLOW_RULES.items()}


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


def _role_map(data_dir: str = "") -> dict:
    """角色中文名 → agent 列表。SoT: role-types.json（store → team-pack → 公开 seed）。"""
    from lib.infra.role_types import role_type_candidates, role_types_sot

    out: dict[str, list[str]] = {}
    for key, entry in (role_types_sot(data_dir) or {}).items():
        disp = (entry or {}).get("display") or {}
        zh = disp.get("zh")
        if not zh:
            continue
        try:
            rt = int(key)
        except (TypeError, ValueError):
            continue
        cands = list(role_type_candidates(rt, data_dir)) if rt else []
        if cands:
            out[zh] = cands
    return out


def get_next_role(current_role: str, conclusion: str):
    return _FLOW_RULES.get((current_role, conclusion))


def pick_person_for_role(role: str, exclude=None, data_dir: str = ""):
    candidates = _role_map(data_dir).get(role, [])
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
    from lib.application.orchestration.dispatch.role_resolver import resolve_agent_for_role_type

    step_action = action or {}
    agent, _ = resolve_agent_for_role_type(
        data_dir, int(role_type), exclude=exclude, pin_agent=pin_agent,
        action=step_action,
    )
    return agent


def get_online_status(data_dir: str = ""):
    return {role: persons for role, persons in _role_map(data_dir).items()}

