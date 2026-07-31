"""Ops: pipeline watchdog pass — anomalies + optional self-heal (tools 业务下沉)."""
from __future__ import annotations

import json
import os
from typing import Any

from lib.application.orchestration.execution import run_orchestrator
from lib.iteration_engine import evaluate_round1_gate
from lib.self_heal import run_self_heal
from lib.tracker import TaskTracker
from lib.utils import json_read


def scheduler_snapshot() -> dict[str, Any]:
    try:
        import urllib.request

        from lib.constants import DEFAULT_API_BASE

        with urllib.request.urlopen(f"{DEFAULT_API_BASE}/api/status", timeout=5) as r:
            return json.loads(r.read()).get("scheduler") or {}
    except Exception:
        return {}


def running_pipeline_summary(data_dir: str) -> list[dict[str, Any]]:
    tr = TaskTracker(data_dir)
    rows: list[dict[str, Any]] = []
    for t in tr.list_all():
        if t.get("status") != "running":
            continue
        tid = t.get("task_id", "")
        if tid.startswith(("remind-", "patrol-", "heartbeat-")):
            continue
        chain = t.get("chain") or []
        step = chain[-1] if chain else {}
        rows.append(
            {
                "task_id": tid,
                "assignee": step.get("to_person") or t.get("assignee"),
                "role": step.get("to_role"),
                "has_result": os.path.exists(os.path.join(data_dir, "msg-results", f"{tid}.json")),
            }
        )
    return rows


def collect_watchdog_context(data_dir: str, agents: dict) -> dict[str, Any]:
    primary = json_read(os.path.join(data_dir, "iterations", "iteration-state.json"), {}).get(
        "primary_task_id", "?"
    )
    gate = evaluate_round1_gate(data_dir, agents)
    sched = scheduler_snapshot()
    scan = (sched.get("jobs") or {}).get("scan") or {}
    return {
        "primary_task_id": primary,
        "gate": gate,
        "scheduler": sched,
        "scan": scan,
        "running": running_pipeline_summary(data_dir),
    }


def run_watchdog_pass(data_dir: str, agents: dict, *, fix: bool = True) -> dict[str, Any]:
    orch = run_orchestrator(data_dir, agents, fix=fix, mode="light")
    if fix:
        orch["healed"] = run_self_heal(data_dir, agents, phase="pre")
    return orch
