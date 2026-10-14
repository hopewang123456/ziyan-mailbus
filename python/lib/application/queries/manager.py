"""Read-side：管理者「待我处理」聚合查询（CQRS-lite，只读不改任务文件）。"""

from __future__ import annotations

from typing import Any, Dict, List

from lib.domain.fsm import TaskFsmState
from lib.infra.role_types import role_type_to_zh

_PLAN_BUCKET = "plan_approval"     # 计划待审批
_ACCEPT_BUCKET = "acceptance"      # 链完成待终验
_COORD_BUCKET = "coordination"     # 异常/阻塞待协调

_TERMINAL_STEP_STATES = {"completed", "skipped", "superseded"}


def _current_step(task: dict) -> Dict[str, Any]:
    """找第一个未终结步骤作为「当前步」，供管理者定位。"""
    for step in task.get("chain") or []:
        state = step.get("fsm_state") or step.get("status") or ""
        if state in _TERMINAL_STEP_STATES:
            continue
        rt = step.get("role_type")
        return {
            "step_id": step.get("step_id") or step.get("step"),
            "role_type": rt,
            "role_zh": role_type_to_zh(int(rt), "") if rt else "",
            "to_agent": step.get("to_agent") or step.get("to_person") or "",
            "state": state,
            "report": step.get("report"),
        }
    return {}


def _bucket_of(task: dict) -> str:
    fsm = task.get("fsm") or {}
    if fsm.get("state") == TaskFsmState.ACCEPTING.value:
        return _ACCEPT_BUCKET
    if fsm.get("substate") == "await_plan_approval":
        return _PLAN_BUCKET
    if fsm.get("substate") == "await_join_review" or fsm.get("reason") == "join_gate_review":
        return _COORD_BUCKET
    if fsm.get("state") in (TaskFsmState.BLOCKED.value, TaskFsmState.FAILED.value):
        return _COORD_BUCKET
    return ""


_ACTIONS_BY_BUCKET = {
    # 动作名映射到既有 /api/tasks/<id>/fsm/{action}
    _PLAN_BUCKET: ["approve-plan", "rollback", "cancel", "priority"],
    _ACCEPT_BUCKET: ["accept", "rollback", "cancel"],
    _COORD_BUCKET: ["approve-join", "continue", "rollback", "skip", "cancel", "priority"],
}


def manager_pending(data_dir: str) -> Dict[str, Any]:
    """聚合三桶待管理者处理的工单。

    只读 TaskTracker.list_all；每项给出可跳转的动作名（均已存在于既有
    fsm action API）。返回结构：
    {
      "total": int,
      "counts": {"plan_approval": n, "acceptance": n, "coordination": n},
      "items": [{task_id, summary, task_type, initiator, tier, priority,
                 status, fsm_state, fsm_substate, bucket, current_step,
                 updated_at, suggested_actions: [...]}]
    }
    """
    from lib.application.orchestration.tracker import TaskTracker

    counts = {_PLAN_BUCKET: 0, _ACCEPT_BUCKET: 0, _COORD_BUCKET: 0}
    items: List[Dict[str, Any]] = []
    for task in TaskTracker(data_dir).list_all():
        bucket = _bucket_of(task)
        if not bucket:
            continue
        fsm = task.get("fsm") or {}
        counts[bucket] += 1
        items.append({
            "task_id": task.get("task_id"),
            "summary": task.get("summary") or task.get("intent") or "",
            "task_type": task.get("task_type"),
            "initiator": task.get("initiator"),
            "tier": task.get("tier"),
            "priority": (fsm or {}).get("priority"),
            "status": task.get("status"),
            "fsm_state": fsm.get("state"),
            "fsm_substate": fsm.get("substate"),
            "fsm_reason": fsm.get("reason"),
            "join_pending": fsm.get("join_pending") if isinstance(fsm.get("join_pending"), dict) else None,
            "bucket": bucket,
            "current_step": _current_step(task),
            "updated_at": task.get("updated_at"),
            "suggested_actions": (
                ["approve-join", "rollback", "cancel"]
                if (fsm.get("substate") == "await_join_review" or fsm.get("reason") == "join_gate_review")
                else _ACTIONS_BY_BUCKET[bucket]
            ),
        })
    items.sort(key=lambda it: (it["priority"] if it["priority"] is not None else 50, it["updated_at"] or ""))
    return {
        "total": len(items),
        "counts": counts,
        "items": items,
    }
