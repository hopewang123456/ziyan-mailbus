"""Workflow 外部 tool 步骤执行。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..external_tools import invoke_tool
from ..utils import _now_iso, json_read


def tool_steps_in_phase(phase: dict) -> List[dict]:
    return [s for s in (phase.get("steps") or []) if s.get("node_type") == "tool"]


def agent_steps_in_phase(phase: dict) -> List[dict]:
    return [s for s in (phase.get("steps") or []) if s.get("node_type") == "agent"]


def pending_tool_id(wf_ext: dict, phase: dict) -> Optional[str]:
    """当前 phase 内 agent 步已走完时，返回待执行 tool_id。"""
    done = set(wf_ext.get("tools_executed") or [])
    for step in (phase.get("steps") or []):
        if step.get("node_type") == "tool":
            tid = step.get("tool_id")
            if tid and tid not in done:
                return tid
        elif step.get("node_type") == "agent":
            continue
    return None


def tool_live_enabled(
    data_dir: str,
    task: dict,
    *,
    gate_id: Optional[str] = None,
    body: Optional[dict] = None,
    gate_def: Optional[dict] = None,
) -> bool:
    """是否以生产模式执行 external tool（默认 dry_run）。"""
    if body and body.get("tool_live"):
        return True
    if gate_def and gate_def.get("tool_live"):
        return True
    wf_ext = (task.get("extensions") or {}).get("ziyan", {}).get("workflow") or {}
    if wf_ext.get("tool_live"):
        return True
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    wf_cfg = cfg.get("mailbus_workflow") or {}
    if wf_cfg.get("tool_live"):
        return True
    allowed = wf_cfg.get("tool_live_gates") or []
    if gate_id and gate_id in allowed:
        return True
    return False


def mark_tool_live_after_gate(task: dict, body: dict, gate_def: dict) -> None:
    """gate approve 后记录 tool_live 意图（供后续 phase 内 tool 步使用）。"""
    on_ap = gate_def.get("on_approve") or {}
    if body.get("tool_live") or gate_def.get("tool_live") or on_ap.get("tool_live"):
        wf_ext = (task.get("extensions") or {}).setdefault("ziyan", {}).setdefault("workflow", {})
        wf_ext["tool_live"] = True


def run_tool_step(
    data_dir: str,
    task: dict,
    tool_id: str,
    *,
    agent_id: str = "mailbus",
    inputs: Optional[dict] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    tid = task.get("task_id") or ""
    payload = inputs or {
        "task_id": tid,
        "intent": task.get("intent") or task.get("summary", ""),
        "workflow_id": (task.get("extensions") or {}).get("ziyan", {}).get("workflow", {}).get("workflow_id"),
    }
    result = invoke_tool(
        data_dir,
        agent_id=agent_id,
        tool_id=tool_id,
        inputs=payload,
        dry_run=dry_run,
    )
    wf_ext = (task.get("extensions") or {}).setdefault("ziyan", {}).setdefault("workflow", {})
    executed = wf_ext.setdefault("tools_executed", [])
    if tool_id not in executed:
        executed.append(tool_id)
    wf_ext.setdefault("tool_results", []).append({
        "tool_id": tool_id,
        "at": _now_iso(),
        "ok": result.get("ok", False),
        "result": result,
    })
    return result
