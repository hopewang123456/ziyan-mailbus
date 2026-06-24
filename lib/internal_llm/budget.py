"""Internal LLM 调用预算 — 按小时 / 任务限流。"""

from __future__ import annotations

import os
import time
from typing import Optional

from ..utils import _now_iso, json_read, json_write


def _budget_path(data_dir: str) -> str:
    return os.path.join(data_dir, "dispatch", "internal-llm-budget.json")


def _load(data_dir: str) -> dict:
    return json_read(_budget_path(data_dir), {"hour": "", "calls": 0, "tasks": {}, "last_fail_at": 0})


def _save(data_dir: str, doc: dict) -> None:
    os.makedirs(os.path.dirname(_budget_path(data_dir)), exist_ok=True)
    json_write(_budget_path(data_dir), doc)


def _hour_key() -> str:
    return _now_iso()[:13]


def check_budget(data_dir: str, task_id: str, cfg: dict) -> Optional[str]:
    """返回错误码或 None 表示可调用。"""
    budget = (cfg or {}).get("budget") or {}
    max_hour = int(budget.get("max_calls_per_hour", 30))
    max_task = int(budget.get("max_calls_per_task", 2))
    cooldown = int(budget.get("cooldown_after_fail_seconds", 300))

    doc = _load(data_dir)
    hk = _hour_key()
    if doc.get("hour") != hk:
        doc = {"hour": hk, "calls": 0, "tasks": {}, "last_fail_at": doc.get("last_fail_at", 0)}

    if doc.get("last_fail_at") and time.time() - doc["last_fail_at"] < cooldown:
        return "llm_cooldown"

    if doc.get("calls", 0) >= max_hour:
        return "llm_budget_hour"

    tc = (doc.get("tasks") or {}).get(task_id, 0)
    if task_id and tc >= max_task:
        return "llm_budget_task"

    return None


def record_call(data_dir: str, task_id: str, *, failed: bool = False) -> None:
    doc = _load(data_dir)
    hk = _hour_key()
    if doc.get("hour") != hk:
        doc = {"hour": hk, "calls": 0, "tasks": {}, "last_fail_at": 0}
    doc["calls"] = doc.get("calls", 0) + 1
    if task_id:
        tasks = doc.setdefault("tasks", {})
        tasks[task_id] = tasks.get(task_id, 0) + 1
    if failed:
        doc["last_fail_at"] = time.time()
    _save(data_dir, doc)
