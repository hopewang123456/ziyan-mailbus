"""step-result 读写 — 避免 transport 层导入 task_fsm。"""
from __future__ import annotations

import os
from typing import Any, Optional

from ..pipeline_results import step_result_path
from ..utils import _now_iso, json_read, json_write


def write_step_result_file(
    data_dir: str,
    task_id: str,
    step_id: str,
    result: dict[str, Any],
    *,
    role_type: Optional[int] = None,
    agent: Optional[str] = None,
) -> str:
    path = step_result_path(data_dir, task_id, step_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dict(result)
    payload.setdefault("task_id", task_id)
    payload.setdefault("step_id", step_id)
    if agent:
        payload.setdefault("agent", agent)
    if role_type is not None:
        payload.setdefault("role_type", role_type)
    if not payload.get("timestamp"):
        payload["timestamp"] = _now_iso()
    json_write(path, payload)
    return path


def read_step_result_file(data_dir: str, task_id: str, step_id: str) -> Optional[dict]:
    path = step_result_path(data_dir, task_id, step_id)
    if not os.path.isfile(path):
        return None
    data = json_read(path, {})
    return data or None
