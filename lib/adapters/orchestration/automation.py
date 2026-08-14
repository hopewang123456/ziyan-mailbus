"""mailbus_automation 重试计数与策略。"""
from __future__ import annotations

from typing import Any


def _retry_bucket(task: dict, key: str) -> dict:
    auto = task.setdefault("automation", {})
    bucket = auto.setdefault("retries", {}).setdefault(key, {})
    return bucket


def bump_retry_count(task: dict, key: str) -> int:
    bucket = _retry_bucket(task, key)
    attempt = int(bucket.get("count") or 0) + 1
    bucket["count"] = attempt
    return attempt


def retry_exceeded(task: dict, config: dict, *, key: str) -> bool:
    auto = config.get("mailbus_automation") or {}
    limits = auto.get("retry_limits") or {}
    max_n = int(limits.get(key) or limits.get("default") or 3)
    bucket = _retry_bucket(task, key)
    return int(bucket.get("count") or 0) >= max_n


def verify_fail_auto_retry(task: dict, config: dict) -> bool:
    auto = config.get("mailbus_automation") or {}
    verify = auto.get("verify") or {}
    return bool(verify.get("auto_retry", True))


def should_auto_approve_plan(envelope: dict, config: dict) -> bool:
    """S 级 code_review / harness 触发任务默认免 plan 审批。"""
    auto = config.get("mailbus_automation") or {}
    if auto.get("auto_approve_plan") is True:
        return True
    task_type = (envelope.get("task_type") or "").lower()
    tier = envelope.get("tier") or "S"
    harness = (envelope.get("extensions") or {}).get("harness") or {}
    if task_type == "code_review" and tier == "S":
        return True
    if harness.get("trigger") == "post-commit-harness" and tier == "S":
        return True
    return False
