"""mailbus 自动化策略 — 可配置的人工/自动边界。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .utils import json_read

_TIER_ORDER = {"S": 0, "M": 1, "L": 2}


def load_automation_config(data_dir: str) -> dict:
    cfg_path = os.path.join(data_dir, "config.json")
    root = json_read(cfg_path, {})
    auto = root.get("mailbus_automation") or {}
    if not isinstance(auto, dict):
        auto = {}
    return auto


def _tier_le(tier: str, ref: str) -> bool:
    return _TIER_ORDER.get((tier or "M").upper(), 1) <= _TIER_ORDER.get((ref or "M").upper(), 1)


def should_auto_approve_plan(envelope: dict, config: Optional[dict] = None) -> bool:
    auto = (config or {}).get("mailbus_automation") or {}
    tiers = auto.get("auto_approve") or {}
    plan_tiers = tiers.get("plan_tiers") or []
    tier = (envelope.get("tier") or "M").upper()
    if tier in plan_tiers:
        return True
    max_tier = tiers.get("plan_tier_max")
    if max_tier and _tier_le(tier, str(max_tier).upper()):
        return True
    return False


def gate_requires_human(gate_id: str, config: Optional[dict] = None) -> bool:
    auto = (config or {}).get("mailbus_automation") or {}
    always = set(auto.get("always_human") or [])
    if gate_id in always:
        return True
    gates = (auto.get("auto_approve") or {}).get("gates") or {}
    if gate_id in gates:
        return not bool(gates[gate_id])
    return True


def test_fail_auto_to_dev(task: dict, config: Optional[dict] = None) -> bool:
    auto = (config or {}).get("mailbus_automation") or {}
    retry = auto.get("auto_retry") or {}
    rule = retry.get("test_fail_to_dev") or {}
    if not rule.get("enabled", True):
        return False
    tiers = rule.get("tiers") or ["S", "M"]
    tier = (task.get("tier") or "M").upper()
    return tier in tiers


def verify_fail_auto_retry(task: dict, config: Optional[dict] = None) -> bool:
    auto = (config or {}).get("mailbus_automation") or {}
    retry = auto.get("auto_retry") or {}
    rule = retry.get("verify_fail_to_dev") or {}
    return bool(rule.get("enabled", True))


def max_retry_attempts(task: dict, config: Optional[dict] = None, key: str = "dev_retry") -> int:
    auto = (config or {}).get("mailbus_automation") or {}
    retry = auto.get("auto_retry") or {}
    if key == "verify_fail":
        rule = retry.get("verify_fail_to_dev") or {}
        return int(rule.get("max_attempts") or 5)
    rule = retry.get("test_fail_to_dev") or {}
    return int(rule.get("max_attempts") or 5)


def bump_retry_count(task: dict, key: str = "dev_retry") -> int:
    fsm = task.setdefault("fsm", {})
    budget = fsm.setdefault("retry_budget", {})
    n = int(budget.get(key) or 0) + 1
    budget[key] = n
    return n


def retry_exceeded(task: dict, config: Optional[dict] = None, key: str = "dev_retry") -> bool:
    fsm = task.get("fsm") or {}
    budget = fsm.get("retry_budget") or {}
    n = int(budget.get(key) or 0)
    return n >= max_retry_attempts(task, config)
