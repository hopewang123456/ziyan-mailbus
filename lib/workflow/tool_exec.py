"""Workflow tool 节点执行（stub / dry-run）。"""
from __future__ import annotations

from typing import Any, Dict, Optional


def tool_live_enabled(
    data_dir: str,
    task: dict,
    *,
    gate_id: str = "",
    body: Optional[dict] = None,
    gate_def: Optional[dict] = None,
) -> bool:
    return False


def run_tool_step(data_dir: str, task: dict, tool_id: str, *, dry_run: bool = True) -> Dict[str, Any]:
    wf_e = (task.get("extensions") or {}).setdefault("ziyan", {}).setdefault("workflow", {})
    executed = set(wf_e.get("tools_executed") or [])
    executed.add(tool_id)
    wf_e["tools_executed"] = sorted(executed)
    return {"ok": True, "tool_id": tool_id, "dry_run": dry_run}


def mark_tool_live_after_gate(task: dict, tool_id: str) -> None:
    wf_e = (task.get("extensions") or {}).setdefault("ziyan", {}).setdefault("workflow", {})
    executed = set(wf_e.get("tools_executed") or [])
    executed.add(tool_id)
    wf_e["tools_executed"] = sorted(executed)
