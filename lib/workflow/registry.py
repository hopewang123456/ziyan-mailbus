"""Workflow registry — store/workflows/registry.json。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ..utils import json_read


def registry_path(data_dir: str) -> str:
    default = os.path.join(data_dir, "workflows", "registry.json")
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    wf_cfg = cfg.get("mailbus_workflow") or {}
    rel = wf_cfg.get("registry_path")
    if not rel:
        return default
    if rel.startswith("store/"):
        root = os.path.dirname(os.path.normpath(data_dir))
        p = os.path.join(root, rel.replace("/", os.sep))
    else:
        p = os.path.join(data_dir, rel.replace("/", os.sep))
    return p if os.path.isfile(p) else default


def load_registry(data_dir: str) -> dict:
    return json_read(registry_path(data_dir), {})


def save_registry(data_dir: str, registry: dict) -> str:
    """写入 workflow registry.json，返回路径。"""
    from ..utils import json_write
    from datetime import date

    path = registry_path(data_dir)
    registry = dict(registry)
    registry["updated_at"] = date.today().isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, registry)
    return path


def get_workflow(registry: dict, workflow_id: str) -> Optional[dict]:
    return (registry.get("workflows") or {}).get(workflow_id)


def resolve_workflow_id(
    task_type: str,
    extensions: dict,
    registry: dict,
) -> str:
    wf_ext = (extensions or {}).get("ziyan.workflow") or {}
    if wf_ext.get("workflow_id"):
        return wf_ext["workflow_id"]
    tt = (task_type or "unknown").lower()
    for wf in (registry.get("workflows") or {}).values():
        if tt in [x.lower() for x in (wf.get("task_types") or [])]:
            return wf["id"]
    return (registry.get("defaults") or {}).get("unknown_task_type_workflow") or "llm_adaptive"


def get_gate_def(workflow: dict, gate_id: str) -> Optional[dict]:
    for g in (workflow or {}).get("gates") or []:
        if g.get("gate_id") == gate_id:
            return g
    return None


def find_phase(workflow: dict, phase_id: str) -> Optional[dict]:
    for p in (workflow or {}).get("phases") or []:
        if p.get("id") == phase_id:
            return p
    return None


def initial_phase_id(workflow: dict) -> Optional[str]:
    phases = (workflow or {}).get("phases") or []
    return phases[0]["id"] if phases else None
