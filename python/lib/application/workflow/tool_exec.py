"""Workflow tool 节点执行（dry-run / live via invoke_tool）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from lib.composition import get_integrations
from lib.infra.utils import json_read


def _wf_ext(task: dict) -> dict:
    return (task.get("extensions") or {}).setdefault("mailbus", {}).setdefault("workflow", {})


def tool_live_enabled(
    data_dir: str,
    task: dict,
    *,
    gate_id: str = "",
    body: Optional[dict] = None,
    gate_def: Optional[dict] = None,
) -> bool:
    body = body or {}
    if body.get("tool_live") is True:
        return True
    wf_e = _wf_ext(task)
    if wf_e.get("tool_live") is True:
        return True
    on_ap = (gate_def or {}).get("on_approve") or {}
    if on_ap.get("tool_live") is True:
        return True
    cfg = json_read(f"{data_dir}/config.json", {})
    wf_cfg = cfg.get("mailbus_workflow") or {}
    if wf_cfg.get("tool_live") is True:
        return True
    gates = wf_cfg.get("tool_live_gates") or []
    if gate_id and gate_id in gates:
        return True
    return False


def mark_tool_live_after_gate(
    task: dict,
    body: Optional[dict] = None,
    gate_def: Optional[dict] = None,
) -> None:
    """Approve 后按 gate / body 打开 task 级 tool_live。"""
    body = body or {}
    gate_def = gate_def or {}
    on_ap = gate_def.get("on_approve") or {}
    if body.get("tool_live") is True or on_ap.get("tool_live") is True:
        _wf_ext(task)["tool_live"] = True


def run_tool_step(
    data_dir: str,
    task: dict,
    tool_id: str,
    *,
    dry_run: bool = True,
    agent_id: str = "mailbus",
    inputs: Optional[dict] = None,
) -> Dict[str, Any]:
    wf_e = _wf_ext(task)
    executed = set(wf_e.get("tools_executed") or [])
    executed.add(tool_id)
    wf_e["tools_executed"] = sorted(executed)
    payload = dict(inputs or {})
    payload.setdefault("task_id", task.get("task_id") or "")
    return get_integrations().invoke_tool(
        data_dir,
        agent_id=agent_id,
        tool_id=tool_id,
        inputs=payload,
        dry_run=dry_run,
    )
