"""Pipeline step result 路径与 I/O — mailbus 框架统一入口。

per-step SoT: msg-results/{task_id}/step-{step_id}.json
legacy 单文件 msg-results/{task_id}.json 仅只读回退（默认关闭写入）。
"""

from __future__ import annotations

import os
from typing import List, Optional

from .utils import json_read


def step_result_dir(data_dir: str, task_id: str) -> str:
    return os.path.join(data_dir, "msg-results", task_id)


def step_result_path(data_dir: str, task_id: str, step_id: str) -> str:
    return os.path.join(step_result_dir(data_dir, task_id), f"step-{step_id}.json")


def legacy_result_path(data_dir: str, task_id: str) -> str:
    return os.path.join(data_dir, "msg-results", f"{task_id}.json")


def _automation_cfg(config: dict) -> dict:
    return (config or {}).get("mailbus_automation") or {}


def legacy_read_enabled(config: dict) -> bool:
    """是否允许从 legacy 单文件回退读取（迁移期）。"""
    return bool(_automation_cfg(config).get("legacy_result_read", True))


def legacy_mirror_enabled(config: dict) -> bool:
    """是否双写 legacy 单文件（默认关）。"""
    return bool(_automation_cfg(config).get("legacy_result_mirror", False))


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
    cfg = config if config is not None else load_config(data_dir)
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
    if legacy_read_enabled(cfg):
        paths.append(legacy_result_path(data_dir, task_id))
    seen = set()
    out: List[str] = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def find_legacy_result_file(data_dir: str, task_id: str) -> Optional[str]:
    """精确 legacy 单文件路径（存在则返回）。"""
    p = legacy_result_path(data_dir, task_id)
    return p if os.path.isfile(p) else None


def read_result_from_paths(paths: List[str]) -> dict:
    for rf in paths:
        if os.path.isfile(rf):
            data = json_read(rf, {})
            if data:
                return data
    return {}
