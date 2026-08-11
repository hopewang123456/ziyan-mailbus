"""Orchestration mediator 鈥?budget FSM (Q8B) + task pause/resume."""
from __future__ import annotations

import os
from typing import Any

from lib.composition import build_orchestration
from lib.domain.errors import PAUSE_REASON_BUDGET, BudgetPaused, NeedsHuman
from lib.domain.fsm import TaskFsmState
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_read, json_write


def can_advance(data_dir: str, task: dict) -> tuple[bool, str]:
    """Gate before pipeline advance. Returns (ok, reason)."""
    orch = build_orchestration(data_dir)
    if orch.budget.is_paused():
        return False, "budget_paused"
    fsm_state = (task.get("fsm") or {}).get("state") or ""
    if fsm_state == TaskFsmState.PAUSED.value:
        return False, "task_paused"
    if not orch.fsm.is_executable(task):
        return False, "not_executable"
    return True, ""


def record_spend(data_dir: str, amount_cny: float, cfg: dict | None = None) -> dict:
    orch = build_orchestration(data_dir)
    cfg = cfg or json_read(os.path.join(data_dir, "config.json"), {})
    prev = orch.budget.load(cfg)
    state = orch.budget.record_spend(amount_cny, cfg)
    if prev.get("fsm_state") != state.get("fsm_state") and state.get("fsm_state") == "awaiting_decision":
        orch.notifier.notify(
            "budget_awaiting_decision",
            {"spent_cny": state.get("spent_cny"), "cap_cny": state.get("cap_cny")},
        )
    return state


def apply_budget_decision(data_dir: str, use_ollama: bool | None, cfg: dict | None = None) -> dict:
    """Q8B: decision 鈫?budget FSM; None pauses chain tasks via Task FSM."""
    orch = build_orchestration(data_dir)
    cfg = cfg or json_read(os.path.join(data_dir, "config.json"), {})
    state = orch.budget.apply_ollama_decision(use_ollama, cfg)
    if state.get("fsm_state") == "paused_budget":
        n = pause_chain_tasks(data_dir, reason=PAUSE_REASON_BUDGET)
        orch.notifier.notify("budget_paused", {"tasks_paused": n})
        state["tasks_paused"] = n
    else:
        n = resume_budget_paused_tasks(data_dir)
        orch.notifier.notify(
            "budget_resumed",
            {"tasks_resumed": n, "force_ollama": state.get("force_ollama")},
        )
        state["tasks_resumed"] = n
    return state


def pause_chain_tasks(data_dir: str, reason: str = PAUSE_REASON_BUDGET) -> int:
    orch = build_orchestration(data_dir)
    tra = TaskTracker(data_dir)
    n = 0
    for t in tra.list_all():
        ensure = orch.fsm.ensure(t)
        st = (ensure.get("fsm") or {}).get("state")
        if st not in (TaskFsmState.EXECUTING.value, TaskFsmState.CREATED.value, ""):
            if (t.get("status") or "") != "running":
                continue
        if st == TaskFsmState.PAUSED.value:
            continue
        if not t.get("chain"):
            continue
        orch.fsm.pause(t, reason=reason)
        tid = t.get("task_id") or t.get("id")
        if tid:
            path = os.path.join(tra.tasks_dir, f"{tid}.json")
            json_write(path, t)
            n += 1
    return n


def resume_budget_paused_tasks(data_dir: str) -> int:
    orch = build_orchestration(data_dir)
    tra = TaskTracker(data_dir)
    n = 0
    for t in tra.list_all():
        if t.get("pause_reason") != PAUSE_REASON_BUDGET:
            continue
        if (t.get("fsm") or {}).get("state") != TaskFsmState.PAUSED.value:
            continue
        orch.fsm.resume(t)
        tid = t.get("task_id") or t.get("id")
        if tid:
            path = os.path.join(tra.tasks_dir, f"{tid}.json")
            json_write(path, t)
            n += 1
    return n


def bump_retry(data_dir: str, task: dict, *, step_id: str = "") -> int:
    orch = build_orchestration(data_dir)
    n = orch.fsm.bump_retry(task, step_id=step_id)
    tid = task.get("task_id") or task.get("id")
    if tid:
        path = os.path.join(data_dir, "tasks", f"{tid}.json")
        if os.path.isfile(path):
            json_write(path, task)
    if n >= 3:
        orch.notifier.notify(
            "retry_escalation",
            {"task_id": tid, "step_id": step_id, "retries": n},
        )
        raise NeedsHuman(f"retry escalation task={tid} step={step_id} n={n}", code="needs_human")
    return n


def require_not_budget_paused(data_dir: str) -> None:
    if build_orchestration(data_dir).budget.is_paused():
        raise BudgetPaused("chain budget paused", code="budget_paused")
