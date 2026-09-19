"""mailbus_automation 重试计数与策略。"""
from __future__ import annotations

from typing import Any

def bump_push_count(task: dict) -> int:
    auto = task.setdefault("automation", {})
    pc = auto.setdefault("pushes", {})
    n = int(pc.get("count") or 0) + 1
    pc["count"] = n
    pc["last_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    return n


def push_budget_blocked(task: dict, data_dir: str, *, config: dict | None = None) -> bool:
    """E2 熔断动作：超预算时置 blocked + 待裁决，返回 True（调用方停止派发）。"""
    import os

    from lib.domain.fsm import TaskFsmState
    from lib.infra.mbus_log import warn
    from lib.infra.utils import json_read

    cfg = config or json_read(os.path.join(data_dir, "config.json"), {})
    allowed, used, limit = push_gate(task, cfg)
    if allowed:
        return False
    fsm = task.setdefault("fsm", {})
    fsm["state"] = TaskFsmState.BLOCKED.value
    fsm["reason"] = f"push_budget_exceeded:{used}/{limit}"
    task["status"] = "blocked"
    tid = task.get("task_id") or task.get("id") or ""
    try:
        # 跨层解耦：adapter→composition 服务（函数级导入避免环）
        from lib.composition import enqueue_human_queue

        enqueue_human_queue(data_dir, {
            "source": "push_budget",
            "task_id": tid,
            "reason": (
                f"单工单 push 次数已达上限 {limit}（已用 {used}）——"
                "为避免 token 黑洞暂停自动派发，请人工裁决：改派 / 挂起 / 提高预算"
            ),
            "severity": "warn",
        })
    except Exception:
        pass
    warn(f"[fsm] push budget exceeded {str(tid)[:24]}: {used}/{limit} -> blocked")
    return True


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


def push_gate(task: dict, config: dict) -> tuple[bool, int, int]:
    """E2 成本熔断：单工单 push 次数预算（默认 6）。

    返回 (allowed, used, limit)。计数在派发成功后 bump_push_count。
    巡检类工单失败反复自动重发的「token 黑洞」在此熔断 → blocked + 待裁决。
    """
    auto = config.get("mailbus_automation") or {}
    limit = int((auto.get("push_limits") or {}).get("per_task") or 6)
    used = int(((task.get("automation") or {}).get("pushes") or {}).get("count") or 0)
    return used < limit, used, limit


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
