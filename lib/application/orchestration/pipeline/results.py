"""Pipeline step result 路径与 I/O — mailbus 框架统一入口。

per-step SoT: msg-results/{task_id}/step-{step_id}.json
"""

from __future__ import annotations

import os
from typing import List, Optional

from lib.infra.utils import json_read


def step_result_dir(data_dir: str, task_id: str) -> str:
    return os.path.join(data_dir, "msg-results", task_id)


def step_result_path(data_dir: str, task_id: str, step_id: str) -> str:
    return os.path.join(step_result_dir(data_dir, task_id), f"step-{step_id}.json")


def load_config(data_dir: str) -> dict:
    return json_read(os.path.join(data_dir, "config.json"), {})


def result_paths_to_try(
    data_dir: str,
    task_id: str,
    step: dict,
    *,
    config: Optional[dict] = None,
) -> List[str]:
    """按优先级返回可能的结果文件路径。"""
    paths: List[str] = []
    sid = step.get("step_id")
    ref = step.get("result_ref")
    if ref and isinstance(ref, str):
        if ref.startswith("msg-results/"):
            paths.append(os.path.join(data_dir, ref.replace("/", os.sep)))
        elif os.path.isabs(ref):
            paths.append(ref)
    if sid:
        paths.append(step_result_path(data_dir, task_id, sid))
    seen = set()
    out: List[str] = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def read_result_from_paths(paths: List[str]) -> dict:
    for rf in paths:
        if os.path.isfile(rf):
            data = json_read(rf, {})
            if data:
                return data
    return {}
