"""Phase 6 — 方案设计步 decomposition / clarifications 门禁。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from lib.infra.constants import MAILBUS_ROOT
from lib.application.orchestration.pipeline.step import step_role_type
from lib.domain.fsm import TaskFsmState
from lib.composition import get_fsm
from lib.infra.utils import _now_iso, json_read

_DEFAULT_CFG = {
    "design_role_types": [1],
    "coding_role_types": [8],
    "require_for_tiers": ["L", "S"],
    "min_planned_steps_for_complex": 3,
    "clarification_conclusions": [
        "clarifications_needed",
        "return_to_owner",
        "needs_clarification",
    ],
}


def load_decomposition_config(data_dir: str = "") -> dict:
    if data_dir:
        cfg = json_read(os.path.join(data_dir, "config.json"), {})
        po = (cfg.get("pipeline_ops") or {}).get("decomposition")
        if isinstance(po, dict) and po:
            return {**_DEFAULT_CFG, **po}
    static = MAILBUS_ROOT / "config" / "pipeline" / "decomposition.json"
    if static.is_file():
        data = json_read(str(static), {})
        if isinstance(data, dict):
            return {**_DEFAULT_CFG, **data}
    return dict(_DEFAULT_CFG)


def extract_decomposition(result: dict) -> Optional[dict]:
    dec = result.get("decomposition")
    if isinstance(dec, dict):
        return dec
    details = result.get("details")
    if isinstance(details, dict):
        dec = details.get("decomposition")
        if isinstance(dec, dict):
            return dec
    return None


def needs_owner_clarification(result: dict, config: Optional[dict] = None) -> bool:
    config = config or _DEFAULT_CFG
    conclusion = (result.get("conclusion") or "").lower()
    if conclusion in (config.get("clarification_conclusions") or []):
        return True
    dec = extract_decomposition(result) or {}
    if dec.get("status") == "clarifications_needed":
        return True
    clar = dec.get("clarifications_needed") or []
    return bool(clar)


def validate_subtasks(subtasks: list) -> Tuple[bool, list[str]]:
    errors: list[str] = []
    if not subtasks:
        return False, ["empty_subtasks"]
    ids: set[str] = set()
    for st in subtasks:
        if not isinstance(st, dict):
            errors.append("subtask_not_object")
            continue
        sid = st.get("id")
        if not sid:
            errors.append("subtask_missing_id")
        elif sid in ids:
            errors.append(f"duplicate_id:{sid}")
        else:
            ids.add(str(sid))
        if st.get("role_type") is None and not st.get("assignee_hint"):
            errors.append(f"subtask_{sid or '?'}_no_assignee")
    for st in subtasks:
        if not isinstance(st, dict):
            continue
        sid = st.get("id")
        for dep in st.get("depends_on") or []:
            if str(dep) not in ids:
                errors.append(f"bad_dep:{dep}_for_{sid}")
    return len(errors) == 0, errors


def topological_subtask_order(subtasks: list) -> list:
    by_id = {str(st["id"]): st for st in subtasks if isinstance(st, dict) and st.get("id")}
    if not by_id:
        return list(subtasks)
    indeg = {i: 0 for i in by_id}
    for st in by_id.values():
        for dep in st.get("depends_on") or []:
            d = str(dep)
            if d in indeg:
                indeg[st["id"]] += 1
    ready = [i for i, d in indeg.items() if d == 0]
    ordered: list = []
    while ready:
        nid = ready.pop(0)
        ordered.append(by_id[nid])
        for st in by_id.values():
            deps = [str(x) for x in (st.get("depends_on") or [])]
            if nid in deps:
                indeg[st["id"]] -= 1
                if indeg[st["id"]] == 0:
                    ready.append(st["id"])
    if len(ordered) != len(by_id):
        return list(subtasks)
    return ordered


def task_requires_decomposition(task: dict, config: dict) -> bool:
    constraints = task.get("constraints") or {}
    if constraints.get("require_decomposition"):
        return True
    tier = (task.get("tier") or "M").upper()
    if tier in (config.get("require_for_tiers") or []):
        return True
    chain = task.get("chain") or []
    head = chain[0] if chain else {}
    planned = head.get("planned_role_types") or []
    coding_types = set(config.get("coding_role_types") or [8])
    coding_count = 0
    for rt in planned:
        try:
            if int(rt) in coding_types:
                coding_count += 1
        except (TypeError, ValueError):
            continue
    min_steps = int(config.get("min_planned_steps_for_complex") or 3)
    if coding_count > 1 or len(planned) >= min_steps:
        return True
    return False


def apply_subtasks_to_chain(task: dict, subtasks: list) -> bool:
    ordered = topological_subtask_order(subtasks)
    chain = task.get("chain") or []
    if not chain:
        return False
    head = chain[0]
    role_types: list[int] = []
    hints: list[str] = []
    for st in ordered:
        try:
            role_types.append(int(st["role_type"]))
        except (TypeError, ValueError, KeyError):
            continue
        hints.append(st.get("assignee_hint") or "")
    if not role_types:
        return False
    head["planned_role_types"] = role_types
    head["planned_subtasks"] = ordered
    head["planned_assignee_hints"] = hints
    task.setdefault("extensions", {}).setdefault("mailbus", {})["decomposition"] = {
        "subtasks": ordered,
        "applied_at": _now_iso(),
    }
    return True


def _enqueue_owner_confirmation(data_dir: str, task: dict, result: dict, *, reason: str) -> str:
    from lib.composition import get_human_gate

    task_id = task.get("task_id") or task.get("id") or ""
    dec = extract_decomposition(result) or {}
    clar = dec.get("clarifications_needed") or []
    return get_human_gate(data_dir).enqueue({
        "type": "owner_confirmation",
        "status": "pending",
        "title": f"待主人确认 · {task_id[:32]}",
        "hint": reason[:120],
        "task_id": task_id,
        "context": {
            "intent": task.get("intent") or task.get("summary", ""),
            "reason": reason,
            "clarifications_needed": clar,
            "step_summary": result.get("summary", ""),
        },
    })


def block_for_clarifications(
    task: dict,
    result: dict,
    *,
    data_dir: str,
    reason: str,
) -> str:
    get_fsm().ensure(task)
    task["fsm"]["state"] = TaskFsmState.BLOCKED.value
    task["fsm"]["substate"] = "await_owner_confirmation"
    task["status"] = "running"
    hq_id = _enqueue_owner_confirmation(data_dir, task, result, reason=reason)
    task["fsm"]["human_queue_id"] = hq_id
    get_fsm().append_history(task, "owner_confirmation", {"reason": reason, "human_queue_id": hq_id})
    return hq_id


def handle_design_step_decomposition(
    task: dict,
    step: dict,
    result: dict,
    *,
    data_dir: str,
) -> Optional[dict]:
    """设计步完成后检查 decomposition；返回 None 表示可继续 FSM。"""
    config = load_decomposition_config(data_dir)
    design_types = set(config.get("design_role_types") or [1])
    rt = step_role_type(step)
    if rt not in design_types:
        return None

    if needs_owner_clarification(result, config):
        return {"action": "clarifications", "reason": "clarifications_needed"}

    if not task_requires_decomposition(task, config):
        dec = extract_decomposition(result) or {}
        if dec.get("status") == "simple":
            return None
        subtasks = dec.get("subtasks") or []
        if subtasks:
            ok, errs = validate_subtasks(subtasks)
            if ok:
                apply_subtasks_to_chain(task, subtasks)
                return {"action": "subtasks_applied", "count": len(subtasks)}
        return None

    dec = extract_decomposition(result) or {}
    if dec.get("status") == "simple":
        return None

    subtasks = dec.get("subtasks") or []
    if not subtasks:
        return {"action": "missing_decomposition", "reason": "complex_task_requires_subtasks"}

    ok, errs = validate_subtasks(subtasks)
    if not ok:
        return {"action": "invalid_decomposition", "errors": errs}

    apply_subtasks_to_chain(task, subtasks)
    return {"action": "subtasks_applied", "count": len(subtasks)}


def coding_push_allowed(task: dict, next_role_type: Optional[int], *, data_dir: str = "") -> Tuple[bool, str]:
    """推开发前二次检查（供 dispatch / push 路径可选调用）。"""
    config = load_decomposition_config(data_dir)
    coding_types = set(config.get("coding_role_types") or [8])
    if next_role_type is None or int(next_role_type) not in coding_types:
        return True, ""
    ext = (task.get("extensions") or {}).get("mailbus", {}).get("decomposition")
    if ext and ext.get("subtasks"):
        return True, ""
    if not task_requires_decomposition(task, config):
        return True, ""
    return False, "missing_decomposition_before_coding"
