"""按 model_tier / prefer_agent 过滤开发工程师候选人。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..model_router import TIER_PRO

DEV_ROLE_TYPE = 8
DEV_CODING_PRO = ("lingyun",)
DEV_CODING_FLASH = ("dali", "lingxiao")


def _pro_allowed_env() -> bool:
    return os.environ.get("MAILBUS_ALLOW_PRO", "").lower() in ("1", "true", "yes")


def _agent_has_pro(agent_id: str, agents_cfg: dict) -> bool:
    models = (agents_cfg.get(agent_id) or {}).get("models") or []
    return TIER_PRO in models


def dispatch_action_from_envelope(envelope: dict) -> dict:
    """从 Envelope 提取派发 action 字段（model_tier / prefer_agent / collab flags）。"""
    if not isinstance(envelope, dict):
        return {}
    constraints = envelope.get("constraints") or {}
    if not isinstance(constraints, dict):
        constraints = {}
    dispatch = constraints.get("dispatch") or {}
    if not isinstance(dispatch, dict):
        dispatch = {}
    action: Dict[str, Any] = {}
    for key in (
        "model_tier", "prefer_agent", "dual_coding", "peer_review", "complexity",
    ):
        if dispatch.get(key) is not None:
            action[key] = dispatch[key]
        elif constraints.get(key) is not None:
            action[key] = constraints[key]
    ext = (envelope.get("extensions") or {}).get("ziyan.dispatch") or {}
    if isinstance(ext, dict):
        for k, v in ext.items():
            action.setdefault(k, v)
    return action


def dispatch_action_from_step(step: dict, task: Optional[dict] = None) -> dict:
    """从 chain step + 可选 task 合并派发 action。"""
    action: Dict[str, Any] = {}
    if task:
        action.update(dispatch_action_from_envelope(task))
    if isinstance(step, dict):
        step_action = step.get("action") or {}
        if isinstance(step_action, dict):
            action.update(step_action)
        for key in ("model_tier", "prefer_agent", "pin_agent"):
            if step.get(key) is not None:
                action[key] = step[key]
    return action


def filter_candidates_by_tier(
    role_type: int,
    candidates: List[str],
    action: Optional[dict],
    agents_cfg: Optional[dict] = None,
) -> List[str]:
    """
    开发工程师（role_type=8）按 tier 过滤；其它 role_type 原样返回。
    空池 fallback 到原 candidates。
    """
    if int(role_type) != DEV_ROLE_TYPE:
        return list(candidates)
    if not candidates:
        return []

    action = action or {}
    agents_cfg = agents_cfg or {}
    prefer = action.get("prefer_agent") or action.get("pin_agent")
    if prefer and prefer in candidates:
        return [prefer]

    model_tier = (action.get("model_tier") or "").lower()
    pro_ok = _pro_allowed_env()

    if model_tier == "pro" and pro_ok:
        pool = list(DEV_CODING_PRO)
        if _agent_has_pro("lingxiao", agents_cfg) and "lingxiao" in candidates:
            pool.append("lingxiao")
        filtered = [c for c in pool if c in candidates]
    else:
        pool = list(DEV_CODING_FLASH)
        if prefer == "lingyun" and "lingyun" in candidates:
            pool.append("lingyun")
        filtered = [c for c in pool if c in candidates]

    if not filtered:
        return list(candidates)
    return filtered
