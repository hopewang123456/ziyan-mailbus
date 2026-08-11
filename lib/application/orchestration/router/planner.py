"""Tier-0 Planner — task_type 规则表 · Tier-1 LLM fallback。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from lib.composition import get_locale, should_auto_approve_plan

# SoT: tier0-planner-spec.md §2
TIER0_RULES: Dict[str, List[int]] = {
    "bugfix": [8, 5, 12],
    "code_review": [5, 12],
    "spike": [3, 1, 9],
    "doc": [1, 9],
    "security_review": [2, 5, 9],
    "ops": [7, 9],
    "video_publish": [3],
    "intake": [4],
    "feature": [1],
    "finance": [10],
    "full_delivery": [1, 3, 1, 9, 8, 8, 2, 5, 6, 7, 11, 12],
}


class PlanError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _apply_constraints(chain: List[int], constraints: dict) -> List[int]:
    if not constraints:
        return chain
    out = list(chain)
    for rt in constraints.get("required_role_types") or []:
        rt = int(rt)
        if rt not in out:
            out.insert(0, rt)
    forbidden = {int(x) for x in (constraints.get("forbidden_role_types") or [])}
    out = [x for x in out if x not in forbidden]
    return out


def _trim_tier_s_bugfix(chain: List[int], tier: str, task_type: str) -> List[int]:
    if tier == "S" and task_type == "bugfix" and 6 in chain:
        return [x for x in chain if x != 6]
    return chain


def _tier0_reason(task_type: str, rt: int) -> str:
    return f"tier0 {task_type} → role_type {rt}"


def _code_review_chain(envelope: dict) -> List[int]:
    """Quality harness code_review — 默认 s1 审阅，涉安加 lingjin，warn/M/L 加终验。"""
    harness = (envelope.get("extensions") or {}).get("harness") or {}
    chain = [5]
    static = harness.get("layers", {}).get("static_analysis") or {}
    semgrep = static.get("semgrep") or {}
    ai = harness.get("layers", {}).get("ai_review") or {}
    summary = (ai.get("summary") or "").lower()
    if semgrep.get("blocking") or int(semgrep.get("findings") or 0) > 0:
        chain.append(7)
    if any(k in summary for k in ("secret", "crypto", "jwt", "password", "token")):
        if 7 not in chain:
            chain.append(7)
    tier = envelope.get("tier") or "S"
    agg = harness.get("aggregate_status") or "warn"
    if tier in ("M", "L") or agg in ("warn", "fail"):
        chain.append(12)
    return chain


def plan_tier0(envelope: dict, *, data_dir: str = "") -> dict:
    """Tier-0 规则表；无匹配时抛 PlanError(plan_failed)。"""
    mode = envelope.get("mode")
    task_type = (envelope.get("task_type") or "unknown").lower()
    tier = envelope.get("tier") or "M"
    constraints = envelope.get("constraints") or {}
    valid_rt = get_locale(data_dir or "").valid_role_types()

    if mode == "explicit":
        planned = envelope.get("planned_chain") or []
        chain = [int(x["role_type"]) for x in planned]
        method = "rules"
        guess = task_type
    else:
        if task_type == "code_review":
            chain = _code_review_chain(envelope)
            method = "rules"
            guess = task_type
        else:
            base = TIER0_RULES.get(task_type)
            if base is None:
                if task_type in ("custom", "unknown"):
                    raise PlanError("plan_failed", f"no tier0 rule for task_type={task_type}")
                raise PlanError("plan_failed", f"unknown task_type={task_type}")
            chain = list(base)
            method = "rules"
            guess = task_type

    chain = _apply_constraints(chain, constraints)
    chain = _trim_tier_s_bugfix(chain, tier, task_type)
    for rt in chain:
        if rt not in valid_rt:
            raise PlanError("schema_invalid", f"invalid role_type={rt}")

    planned_chain = [
        {"role_type": rt, "reason": _tier0_reason(guess, rt)}
        for rt in chain
    ]
    skipped = sorted(set(valid_rt) - set(chain))

    return {
        "planned_chain": planned_chain,
        "plan_meta": {
            "method": method,
            "task_type_guess": guess,
            "confidence": 1.0,
            "skipped_role_types": skipped,
            "provider_used": "rules",
        },
    }


def _llm_cfg(config: Optional[dict], data_dir: str) -> dict:
    if config and "mailbus_internal_llm" in config:
        return config.get("mailbus_internal_llm") or {}
    from lib.application.internal_llm.planner import load_llm_config
    return load_llm_config(data_dir)


def plan_task(
    envelope: dict,
    *,
    data_dir: str = "",
    config: Optional[dict] = None,
) -> dict:
    """Tier-0 → Tier-1 fallback；返回 a2a-planner-output 形状。"""
    try:
        return plan_tier0(envelope, data_dir=data_dir)
    except PlanError as exc:
        if exc.code != "plan_failed":
            raise
        cfg = _llm_cfg(config, data_dir)
        triggers = cfg.get("triggers") or {}
        if not cfg.get("enabled") or not triggers.get("plan_task", True):
            raise
        from lib.application.internal_llm.planner import plan_with_llm
        return plan_with_llm(envelope, data_dir=data_dir, config=cfg)


def plan_replan(
    envelope: dict,
    *,
    data_dir: str = "",
    config: Optional[dict] = None,
) -> dict:
    """Deny 后重规划 — 强制 Tier-1 LLM + RAG（不走 Tier-0 规则表）。"""
    cfg = _llm_cfg(config, data_dir)
    triggers = cfg.get("triggers") or {}
    if not cfg.get("enabled"):
        raise PlanError("plan_failed", "internal_llm disabled")
    if not triggers.get("replan", True):
        raise PlanError("plan_failed", "triggers.replan disabled")
    from lib.application.internal_llm.planner import plan_with_llm
    return plan_with_llm(envelope, data_dir=data_dir, config=cfg)


def needs_plan_approval(envelope: dict, config: Optional[dict] = None) -> bool:
    if envelope.get("await_plan_approval"):
        return True
    if config and should_auto_approve_plan(envelope, config):
        return False
    cfg = (config or {}).get("mailbus_internal_llm") if config and "mailbus_internal_llm" in config else _llm_cfg(config, "")
    guard = cfg.get("guardrails") or {}
    tier_min = guard.get("await_plan_approval_tier_min", "M")
    tier = envelope.get("tier") or "S"
    order = {"S": 0, "M": 1, "L": 2}
    return order.get(tier, 1) >= order.get(tier_min, 1)
