"""Router dispatch — start_executing / await_plan_approval / first-step inbox push."""

from __future__ import annotations

from lib.application.orchestration.step_dispatch import dispatch_fsm_step
from lib.composition import get_fsm
from lib.domain.fsm import TaskFsmState
from lib.infra.utils import json_write


def _fsm():
    return get_fsm()


def set_await_plan_approval(task: dict) -> None:
    _fsm().ensure(task)
    task["fsm"]["state"] = TaskFsmState.CREATED.value
    task["fsm"]["substate"] = "await_plan_approval"
    task["status"] = "pending"


def start_executing(task: dict) -> None:
    _fsm().ensure(task)
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"].pop("substate", None)
    task["fsm"].pop("gate_id", None)
    task["status"] = "running"


def _collab_sibling_summary(task: dict) -> str:
    return task.get("intent") or task.get("summary") or ""


def _dispatch_collab_siblings(data_dir: str, task: dict) -> int:
    """物化并并发推送 collab 并行组除首成员外的兄弟步骤（P0-1 引擎侧）。

    返回成功推送数；任一失败抛 RuntimeError，由调用方转入 blocked。
    """
    chain = task.get("chain") or []
    if not chain:
        return 0
    meta = chain[0].get("collab_join") or {}
    if not meta:
        return 0
    from lib.infra.utils import _now_iso
    from lib.infra.role_types import role_type_to_zh

    tid = task.get("task_id") or task.get("id") or ""
    gid = meta.get("group_id") or "g1"
    pushed = 0
    for i, member in enumerate(meta.get("members") or []):
        if i == 0:
            continue
        rt = int(member["role_type"])
        pin = member.get("pin_agent")
        from lib.application.orchestration.dispatch.role_resolver import resolve_agent_for_role_type

        agent_id, dmeta = resolve_agent_for_role_type(data_dir, rt, pin_agent=pin)
        if not agent_id:
            raise RuntimeError(f"collab sibling role_type={rt} no assignee")
        sn = len(chain) + pushed + 1
        sid = f"{chain[0].get('step_id') or 's1'}.p{i}"
        step = {
            "step": sn,
            "step_id": sid,
            "role_type": rt,
            "to_role": role_type_to_zh(rt, data_dir),
            "to_person": agent_id,
            "to_agent": agent_id,
            "dispatch_meta": dmeta,
            "fsm_state": "queued",
            "status": "running",
            "started_at": _now_iso(),
            "completed_at": None,
            "report": None,
            "result_consumed": False,
            "task_id": tid,
            "result_ref": f"msg-results/{tid}/step-{sid}.json",
            "parallel_group": gid,
            "collab_join": meta,
        }
        from lib.application.orchestration.step_dispatch import dispatch_fsm_step

        ok = dispatch_fsm_step(
            data_dir, tid, step, summary=_collab_sibling_summary(task),
        )
        if not ok:
            raise RuntimeError(f"collab sibling {sid} dispatch failed")
        _fsm().mark_step_dispatched(step)
        chain.append(step)
        pushed += 1
    return pushed


def _push_budget_blocked(task: dict, data_dir: str, tid: str) -> bool:
    """E2：单工单 push 预算熔断 — 超限转 blocked + 待裁决，不再自动派发。"""
    from lib.adapters.orchestration.automation import push_budget_blocked

    return push_budget_blocked(task, data_dir)


def dispatch_first_step(data_dir: str, task: dict) -> bool:
    """Push chain[0] to assignee inbox; mark step dispatched."""
    chain = task.get("chain") or []
    if not chain:
        return False
    step = chain[0]
    tid = task.get("task_id") or task.get("id") or ""
    if not step.get("to_agent") and not step.get("to_person"):
        try:
            from lib.application.orchestration.dispatch.role_resolver import resolve_agent_for_role_type

            rt = int(step.get("role_type") or 0)
            pin = step.get("pin_agent") or step.get("agent_id")
            agent_id, meta = resolve_agent_for_role_type(data_dir, rt, pin_agent=pin)
            if agent_id:
                step["to_agent"] = agent_id
                step["dispatch_meta"] = meta
        except Exception:
            pass

    if _push_budget_blocked(task, data_dir, tid):
        try:
            from lib.application.orchestration.tracker import TaskTracker

            tr = TaskTracker(data_dir)
            json_write(tr._task_path(tid), task)
        except Exception:
            pass
        return False

    ok = dispatch_fsm_step(
        data_dir,
        tid,
        step,
        summary=task.get("intent") or task.get("summary") or "",
    )
    if not ok:
        # P10：派发失败不能静默——任务落盘 blocked，避免「报 ok 但工单悬空」。
        _fsm().ensure(task)
        task["fsm"]["state"] = TaskFsmState.BLOCKED.value
        task["fsm"]["reason"] = "first_step_dispatch_failed"
        task["status"] = "blocked"
        try:
            from lib.application.orchestration.tracker import TaskTracker

            tr = TaskTracker(data_dir)
            json_write(tr._task_path(tid), task)
        except Exception:
            pass
        return False
    from lib.adapters.orchestration.automation import bump_push_count

    bump_push_count(task)
    if ok:
        _fsm().mark_step_dispatched(step)
        task["fsm"]["active_step_id"] = step.get("step_id")
        task["assignee"] = step.get("to_agent") or step.get("to_person") or ""
        try:
            # P0-1：collab 并行组 —— 首步成功派发后，并发推送兄弟步骤
            _dispatch_collab_siblings(data_dir, task)
        except Exception as exc:  # 兄弟派发失败 → 任务转 blocked，交管理者协调
            from lib.infra.mbus_log import warn

            warn(f"[fsm] collab sibling dispatch failed {tid[:24]}: {exc}")
            _fsm().ensure(task)
            task["fsm"]["state"] = TaskFsmState.BLOCKED.value
            task["fsm"]["reason"] = f"collab_dispatch_failed: {exc}"
            task["status"] = "blocked"
            try:
                from lib.application.orchestration.tracker import TaskTracker

                tr = TaskTracker(data_dir)
                json_write(tr._task_path(tid), task)
            except Exception:
                pass
            return False
        try:
            from lib.application.orchestration.tracker import TaskTracker

            tr = TaskTracker(data_dir)
            json_write(tr._task_path(tid), task)
        except Exception:
            pass
    return ok
