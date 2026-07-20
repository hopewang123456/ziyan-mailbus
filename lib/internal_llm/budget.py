"""Internal LLM 调用预算（轻量文件计数）。"""

from __future__ import annotations

import os
import time

from ..utils import json_read, json_write


def _budget_path(data_dir: str) -> str:
    return os.path.join(data_dir, "runtime", "internal-llm-budget.json")


def check_budget(data_dir: str, task_id: str, cfg: dict) -> str | None:
    limits = cfg.get("budget") or {}
    max_task = int(limits.get("max_calls_per_task") or 0)
    max_hour = int(limits.get("max_calls_per_hour") or 0)
    if max_task <= 0 and max_hour <= 0:
        return None

    state = json_read(_budget_path(data_dir), {"tasks": {}, "hour": {}})
    now = int(time.time())
    hour_key = time.strftime("%Y%m%d%H", time.localtime(now))

    if max_task > 0 and task_id:
        count = int((state.get("tasks") or {}).get(task_id) or 0)
        if count >= max_task:
            return f"budget exceeded: task {task_id} ({count}/{max_task})"

    if max_hour > 0:
        hour_count = int((state.get("hour") or {}).get(hour_key) or 0)
        if hour_count >= max_hour:
            return f"budget exceeded: hour ({hour_count}/{max_hour})"

    return None


def record_call(data_dir: str, task_id: str, *, failed: bool = False) -> None:
    if failed:
        return
    path = _budget_path(data_dir)
    state = json_read(path, {"tasks": {}, "hour": {}})
    now = int(time.time())
    hour_key = time.strftime("%Y%m%d%H", time.localtime(now))
    tasks = state.setdefault("tasks", {})
    hour = state.setdefault("hour", {})
    if task_id:
        tasks[task_id] = int(tasks.get(task_id) or 0) + 1
    hour[hour_key] = int(hour.get(hour_key) or 0) + 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, state)
