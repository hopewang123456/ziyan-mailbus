"""Task / Step 显式状态机 — 替换隐式 pipeline_step 流转。

设计目标：
- 任务级 + 步骤级双层状态，Dashboard/API 可直接展示
- 支持回退（方案不合格）、跳过、取消
- 每步独立 result_ref，避免单文件覆盖误判
- 多任务并行时按 priority 排序调度
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from lib.composition import get_next_role, pick_person_for_role  # 跨层解耦
from lib.domain.pipeline_step import (
    is_role_pipeline_task,
    planned_agents_remaining,
    planned_role_types_remaining,
    step_agent,
    step_role_type,
)
from lib.domain.fsm import StepFsmState, TaskFsmState
from lib.infra.constants import PROJECT_ROOT_STR
from lib.infra.utils import _now_iso, json_read, json_write, parse_iso_dt

# ── 状态枚举：定义在 lib.domain.fsm（此处再导出供既有 import）─────────────

# 结论 → 是否视为步骤完成（可流转）
_DONE_CONCLUSIONS = frozenset({
    "done", "pass", "approved", "fail", "dispatched", "rejected",
    "need_research", "blocked", "warning",
    "clarifications_needed", "return_to_owner", "needs_clarification",
})

# 结论 → 任务进入 blocked（需人工或自动回退）
_BLOCKING_CONCLUSIONS = frozenset({
    "fail", "rejected", "blocked", "warning",
})

# legacy chain.status → fsm_state
_LEGACY_TO_FSM = {
    "running": StepFsmState.AWAITING_RESULT,
    "processing": StepFsmState.IN_PROGRESS,
    "completed": StepFsmState.COMPLETED,
    "done": StepFsmState.COMPLETED,
    "failed": StepFsmState.FAILED,
    "skipped": StepFsmState.SKIPPED,
}


# ── 路径与 ID（re-export 框架层）──────────────────────────────────────────

from lib.infra.pipeline_results import (
    load_config as load_pipeline_config,
    result_paths_to_try,
    step_result_dir,
    step_result_path,
)


def _make_step_id(step_num: int, attempt: int = 1) -> str:
    return f"s{step_num}a{attempt}" if attempt > 1 else f"s{step_num}"


def _parse_step_num(step: dict, chain: List[dict]) -> int:
    n = step.get("step")
    if n is not None:
        return int(n)
    try:
        return chain.index(step) + 1
    except ValueError:
        return len(chain)


# ── 迁移 / 规范化 ─────────────────────────────────────────────────────────

def ensure_fsm(task: dict, *, default_priority: int = 50) -> dict:
    """为 task / chain 补全 fsm 字段（幂等）。"""
    chain = task.get("chain") or []
    fsm = task.get("fsm") or {}
    if not fsm.get("state"):
        status = (task.get("status") or "running").lower()
        if status == "success":
            fsm["state"] = TaskFsmState.SUCCEEDED.value
        elif status in ("cancelled", "failed", "timeout"):
            fsm["state"] = TaskFsmState.FAILED.value if status == "failed" else TaskFsmState.CANCELLED.value
        elif status == "paused":
            fsm["state"] = TaskFsmState.PAUSED.value
        else:
            fsm["state"] = TaskFsmState.EXECUTING.value
    fsm.setdefault("version", 1)
    fsm.setdefault("priority", default_priority)
    fsm.setdefault("history", [])

    for i, step in enumerate(chain):
        if not isinstance(step, dict):
            continue
        sn = _parse_step_num(step, chain)
        step.setdefault("step", sn)
        step.setdefault("step_id", _make_step_id(sn, int(step.get("attempt") or 1)))
        legacy = (step.get("status") or "running").lower()
        if not step.get("fsm_state"):
            step["fsm_state"] = _LEGACY_TO_FSM.get(legacy, StepFsmState.PENDING).value
        step.setdefault("attempt", 1)
        tid = task.get("task_id") or task.get("id") or ""
        if tid and not step.get("result_ref"):
            step["result_ref"] = f"msg-results/{tid}/step-{step['step_id']}.json"
        # legacy status 与 fsm 同步（running 步骤）
        if step.get("fsm_state") in (
            StepFsmState.QUEUED.value,
            StepFsmState.DISPATCHED.value,
            StepFsmState.IN_PROGRESS.value,
            StepFsmState.AWAITING_RESULT.value,
        ):
            step["status"] = "running"

    active = get_active_step(task)
    fsm["active_step_id"] = active.get("step_id") if active else fsm.get("active_step_id")
    task["fsm"] = fsm
    return task


def get_active_step(task: dict) -> Optional[dict]:
    """当前活跃步骤：优先 fsm.active_step_id（非终态）；否则最后一个非终态节点。"""
    chain = task.get("chain") or []
    terminal = {
        StepFsmState.COMPLETED.value,
        StepFsmState.FAILED.value,
        StepFsmState.SKIPPED.value,
        StepFsmState.SUPERSEDED.value,
    }
    aid = (task.get("fsm") or {}).get("active_step_id")
    if aid:
        for step in chain:
            if not isinstance(step, dict):
                continue
            if (step.get("step_id") or step.get("step")) == aid:
                fs = step.get("fsm_state") or step.get("status", "")
                if fs not in terminal:
                    return step
                break
    for step in reversed(chain):
        if not isinstance(step, dict):
            continue
        fs = step.get("fsm_state") or step.get("status", "")
        if fs not in terminal:
            return step
    return chain[-1] if chain else None


def resolve_step_for_agent(task: dict, agent: str | None = None) -> Optional[dict]:
    """改派/回写时定位步骤：优先匹配 agent 的非终态并行成员，再回退 get_active_step。"""
    if agent:
        terminal = {
            StepFsmState.COMPLETED.value,
            StepFsmState.FAILED.value,
            StepFsmState.SKIPPED.value,
            StepFsmState.SUPERSEDED.value,
        }
        for step in task.get("chain") or []:
            if not isinstance(step, dict):
                continue
            who = step.get("to_agent") or step.get("to_person") or ""
            if who != agent:
                continue
            fs = step.get("fsm_state") or step.get("status") or ""
            if fs not in terminal:
                return step
    return get_active_step(task)


def task_priority(task: dict) -> int:
    """数值越小优先级越高。"""
    fsm = task.get("fsm") or {}
    p = fsm.get("priority", 50)
    try:
        return int(p)
    except (TypeError, ValueError):
        return 50


def is_task_executable(task: dict) -> bool:
    status = (task.get("status") or "")
    if status in ("cancelled", "success", "failed", "timeout"):
        return False
    st = (task.get("fsm") or {}).get("state") or ""
    if st:
        if st == TaskFsmState.EXECUTING.value:
            return True
        if st == TaskFsmState.CREATED.value and status == "running":
            return True
        return False
    return status == "running"


# ── 步骤结果读写 ─────────────────────────────────────────────────────────

def _normalize_result_timestamp(step: dict, ts: str) -> str:
    """禁止 agent 填早于 started_at 的历史 timestamp。"""
    now = _now_iso()
    started = step.get("started_at") or ""
    out = ts or now
    if not started:
        return out
    try:
        if parse_iso_dt(out) < parse_iso_dt(started):
            return now
    except Exception:
        return now
    return out


def result_mtime_ok(
    data_dir: str, task_id: str, step: dict, result: dict,
) -> bool:
    """result timestamp / 文件 mtime 须不早于 step.started_at。"""
    from datetime import datetime, timezone

    step_started = step.get("started_at") or ""
    result_ts = result.get("timestamp") or result.get("updated_at") or ""
    if step_started and result_ts:
        try:
            return parse_iso_dt(result_ts) >= parse_iso_dt(step_started)
        except Exception:
            return True
    if step_started:
        cfg = load_pipeline_config(data_dir)
        paths_to_try = result_paths_to_try(data_dir, task_id, step, config=cfg)
        for rf in paths_to_try:
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(rf), tz=timezone.utc)
                return mtime >= parse_iso_dt(step_started)
            except OSError:
                continue
    return True


def write_step_result(
    data_dir: str, task_id: str, step: dict, result: dict, *, immediate_advance: bool = True,
) -> str:
    """写入 per-step 结果（SoT）。"""
    sid = step.get("step_id") or _make_step_id(_parse_step_num(step, []))
    path = step_result_path(data_dir, task_id, sid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dict(result)
    payload.setdefault("task_id", task_id)
    payload.setdefault("step_id", sid)
    payload.setdefault("pipeline_step", step.get("step"))
    payload["timestamp"] = _normalize_result_timestamp(step, payload.get("timestamp") or "")
    json_write(path, payload)
    if immediate_advance:
        _maybe_immediate_pipeline(data_dir, task_id)
    return path


def archive_step_result_for_retry(
    data_dir: str, task_id: str, step: dict, result: dict,
) -> Optional[str]:
    """验证失败重试时归档旧结果，避免 pipeline 重复消费。"""
    sid = step.get("step_id") or ""
    if not sid:
        return None
    failed_dir = os.path.join(step_result_dir(data_dir, task_id), "failed")
    os.makedirs(failed_dir, exist_ok=True)
    stamp = (_now_iso() or "").replace(":", "").replace("+", "")
    dst = os.path.join(failed_dir, f"{sid}-{stamp}.json")
    json_write(dst, result)
    src = step_result_path(data_dir, task_id, sid)
    if os.path.isfile(src):
        try:
            os.remove(src)
        except OSError:
            pass
    return dst


def revert_failed_retry(
    data_dir: str,
    task_id: str,
    step: dict,
    result: dict,
    archived_path: Optional[str] = None,
) -> None:
    """verify retry 推送失败时：恢复已归档的 step result，保持步骤 awaiting_result。"""
    sid = step.get("step_id") or ""
    if archived_path and os.path.isfile(archived_path) and sid:
        dst = step_result_path(data_dir, task_id, sid)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        json_write(dst, result)
    elif result and sid:
        json_write(step_result_path(data_dir, task_id, sid), result)
    step["status"] = "running"
    step["fsm_state"] = StepFsmState.AWAITING_RESULT.value
    step["result_consumed"] = False
    step.pop("completed_at", None)


def _maybe_immediate_pipeline(data_dir: str, task_id: str) -> None:
    """G-02：写结果后立即推进 pipeline，不等待 scan 周期。"""
    try:
        cfg = json_read(os.path.join(data_dir, "config.json"), {})
        auto = cfg.get("mailbus_automation") or {}
        if auto.get("immediate_pipeline_dispatch", True) is False:
            return
        from lib.composition import trigger_task
        from lib.infra.utils import resolve_paths

        agents = cfg.get("agents") or {}
        trigger_task(data_dir, task_id, agents, resolve_paths(data_dir))
    except Exception:
        pass


def read_step_result(data_dir: str, task_id: str, step: dict) -> Optional[dict]:
    from lib.infra.pipeline_results import read_result_from_paths, result_paths_to_try

    paths = result_paths_to_try(data_dir, task_id, step)
    data = read_result_from_paths(paths)
    return data or None


def result_applies_to_step(
    result: dict,
    task_id: str,
    step: dict,
    chain: List[dict],
    *,
    result_mtime_ok: bool = True,
) -> Tuple[bool, str]:
    """校验结果是否对应当前活跃步骤。"""
    rid = result.get("task_id") or result.get("task") or ""
    if rid and rid != task_id:
        return False, "wrong_task"

    src = (result.get("source") or "").lower()
    if "auto-linked-from" in src or "auto-recovered-from" in src:
        return False, "untrusted_source"

    step_num = _parse_step_num(step, chain)
    sid = step.get("step_id")
    if result.get("step_id") and sid and result.get("step_id") != sid:
        return False, "wrong_step_id"

    rstep = result.get("pipeline_step")
    if rstep is not None:
        if int(rstep) < step_num:
            return False, "stale_prior_step"
        if int(rstep) != step_num:
            return False, "wrong_step"

    agent = result.get("agent") or result.get("from") or ""
    expected = step.get("to_agent") or step.get("to_person", "")
    if agent and expected and agent != expected:
        return False, "wrong_agent"

    c = (result.get("conclusion") or "").lower()
    if c not in _DONE_CONCLUSIONS and result.get("status") != "completed":
        return False, "inconclusive"

    if not result_mtime_ok:
        return False, "stale_timestamp"

    return True, "ok"


# ── 状态转移 ─────────────────────────────────────────────────────────────

def _append_history(task: dict, event: str, detail: dict) -> None:
    hist = task.setdefault("fsm", {}).setdefault("history", [])
    hist.append({"at": _now_iso(), "event": event, **detail})
    if len(hist) > 100:
        task["fsm"]["history"] = hist[-100:]


def mark_step_dispatched(step: dict) -> None:
    step["fsm_state"] = StepFsmState.DISPATCHED.value
    step["status"] = "running"
    step.setdefault("started_at", _now_iso())


def mark_step_awaiting_result(step: dict) -> None:
    step["fsm_state"] = StepFsmState.AWAITING_RESULT.value
    step["status"] = "running"


def complete_step(step: dict, report: dict) -> None:
    step["fsm_state"] = StepFsmState.COMPLETED.value
    step["status"] = "completed"
    step["completed_at"] = _now_iso()
    step["report"] = report
    step["result_consumed"] = True


def fail_step(step: dict, reason: str = "") -> None:
    step["fsm_state"] = StepFsmState.FAILED.value
    step["status"] = "failed"
    step["completed_at"] = _now_iso()
    if reason:
        step["fail_reason"] = reason


def supersede_step(step: dict) -> None:
    step["fsm_state"] = StepFsmState.SUPERSEDED.value
    step["status"] = "done"


def create_next_step(
    task: dict,
    *,
    to_role: str,
    to_person: str,
    from_role: str,
    from_person: str,
    rollback_from: Optional[str] = None,
    reason: str = "",
    role_type: Optional[int] = None,
) -> dict:
    chain = task.get("chain") or []
    prev = chain[-1] if chain else {}
    sn = len(chain) + 1
    attempt = 1
    if rollback_from:
        m = re.search(r"s(\d+)", rollback_from)
        if m:
            sn = int(m.group(1))
        attempt = int(prev.get("attempt") or 1) + 1
    sid = _make_step_id(sn, attempt)
    tid = task.get("task_id") or task.get("id") or ""
    step = {
        "step": sn,
        "step_id": sid,
        "attempt": attempt,
        "from_role": from_role,
        "from_person": from_person,
        "from_agent": from_person,
        "to_role": to_role,
        "to_person": to_person,
        "to_agent": to_person,
        "action": f"等待{to_role}处理",
        "fsm_state": StepFsmState.QUEUED.value,
        "status": "running",
        "started_at": _now_iso(),
        "completed_at": None,
        "report": None,
        "result_consumed": False,
        "task_id": tid,
        "result_ref": f"msg-results/{tid}/step-{sid}.json",
    }
    if role_type is not None:
        step["role_type"] = int(role_type)
    if rollback_from:
        step["rollback_from"] = rollback_from
        step["rollback_reason"] = reason
    return step


def resolve_transition(
    chain: List[dict],
    result: dict,
    current_role: str,
    conclusion: str,
    agents: Optional[dict] = None,
    *,
    data_dir: str = "",
) -> Tuple[Optional[str], Optional[str], str]:
    """返回 (next_role, next_person, kind)。kind: advance|terminal|blocked。"""
    from lib.composition import resolve_next_assignee, is_pipeline_terminal

    if not data_dir:
        data_dir = os.path.join(PROJECT_ROOT_STR, "store")

    n_role, n_person = resolve_next_assignee(
        chain, result, current_role, conclusion, agents, data_dir=data_dir,
    )
    if n_role and n_person:
        return n_role, n_person, "advance"
    if planned_role_types_remaining(chain) or planned_agents_remaining(chain):
        return None, None, "blocked"
    crt_rt = step_role_type(chain[-1]) if chain else None
    if is_pipeline_terminal(
        current_role, conclusion, chain,
        data_dir=data_dir, current_role_type=crt_rt,
    ):
        return None, None, "terminal"
    if (conclusion or "").lower() in _BLOCKING_CONCLUSIONS:
        from lib.composition import next_role_after
        crt_rt = step_role_type(chain[-1]) if chain else None
        nxt = next_role_after(
            current_role, conclusion, data_dir,
            current_role_type=int(crt_rt) if crt_rt is not None else None,
        )
        return nxt, pick_person_for_role(nxt or "", exclude=None, data_dir=data_dir), "rollback_flow"
    return None, None, "blocked"


def _advance_collab_join(
    task: dict,
    step: dict,
    chain: List[dict],
    current_role: str,
    to_person: str,
    summary: str,
    cj: dict,
    *,
    data_dir: str,
) -> Dict[str, Any]:
    """并行组全部完成后创建 join 步骤并 advance。"""
    from lib.infra.role_types import role_type_to_zh
    from lib.composition import pick_person_for_role

    join_role = role_type_to_zh(int(cj["join_role_type"]), data_dir)
    join_person = pick_person_for_role(
        join_role,
        exclude={s.get("to_person") for s in chain if s.get("to_person")},
        data_dir=data_dir,
    )
    if not join_person:
        task["fsm"]["state"] = TaskFsmState.BLOCKED.value
        return {"ok": False, "error": "no_assignee", "action": "blocked", "reason": "no_join_assignee"}
    nxt = create_next_step(
        task,
        to_role=join_role,
        to_person=join_person,
        from_role=current_role,
        from_person=to_person,
        reason=(summary or "collab join")[:200],
        role_type=int(cj["join_role_type"]),
    )
    chain.append(nxt)
    task["assignee"] = join_person
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"]["active_step_id"] = nxt["step_id"]
    task["fsm"].pop("substate", None)
    task["fsm"].pop("join_pending", None)
    if task["fsm"].get("reason") in ("join_gate_review", "join_gate_not_supported"):
        task["fsm"].pop("reason", None)
    task["status"] = "running"
    _append_history(task, "advance", {
        "from_step": step.get("step_id"),
        "to_step": nxt["step_id"],
        "to_person": join_person,
        "kind": "collab_join",
    })
    return {
        "ok": True,
        "action": "advance",
        "next_step": nxt,
        "next_person": join_person,
        "next_role": join_role,
        "task": task,
    }


def apply_approve_join(
    task: dict,
    body: Optional[dict] = None,
    *,
    data_dir: str = "",
) -> Dict[str, Any]:
    """管理者批准 collab join_gate=review 后推进汇合步骤。"""
    ensure_fsm(task)
    fsm = task.get("fsm") or {}
    if fsm.get("substate") != "await_join_review" and fsm.get("reason") != "join_gate_review":
        return {"ok": False, "error": "not_awaiting_join_review", "action": "noop"}
    cj_meta = fsm.get("join_pending") or {}
    chain = task.get("chain") or []
    step = None
    cj: dict = {}
    for s in reversed(chain):
        if s.get("collab_join") and s.get("parallel_group"):
            step = s
            cj = dict(s.get("collab_join") or {})
            break
    if not step or not cj:
        return {"ok": False, "error": "no_collab_join_meta", "action": "blocked"}
    if cj_meta.get("join_role_type") is not None:
        cj["join_role_type"] = cj_meta.get("join_role_type") or cj.get("join_role_type")
    current_role = step.get("to_role") or ""
    to_person = step.get("to_person") or step.get("to_agent") or ""
    note = (body or {}).get("reason") or "manager approve join"
    out = _advance_collab_join(
        task, step, chain, current_role, to_person, note, cj, data_dir=data_dir,
    )
    if out.get("ok"):
        _append_history(task, "approve_join", {"reviewer": (body or {}).get("reviewer") or "manager"})
    return out


def apply_submit(
    task: dict,
    result: dict,
    *,
    agents: Optional[dict] = None,
    data_dir: str = "",
) -> Dict[str, Any]:
    """处理步骤结果提交 → 完成当前步 / 推进 / 阻塞 / 终态。"""
    ensure_fsm(task)
    step = resolve_step_for_agent(task, result.get("agent"))
    if not step:
        return {"ok": False, "error": "no_active_step"}

    chain = task.get("chain") or []
    tid = task.get("task_id") or task.get("id") or ""
    mtime_ok = result_mtime_ok(data_dir, tid, step, result) if data_dir else True
    ok, reason = result_applies_to_step(
        result, tid, step, chain, result_mtime_ok=mtime_ok,
    )
    if not ok:
        return {"ok": False, "error": reason}

    conclusion = (result.get("conclusion") or "done").lower()
    # step_role_zh 回退链：step.to_role → role_type→zh dict → 默认 "方案设计师"
    # 这里不需要 chain._agent_role_map（agent 名回退），因为 step.get("to_role") 已覆盖主流场景。
    from lib.domain.pipeline_step import _ROLE_TYPE_ZH as _STEP_ROLE_ZH
    rt_fallback = step.get("role_type")
    role_fallback = _STEP_ROLE_ZH.get(int(rt_fallback), "方案设计师") if rt_fallback is not None else "方案设计师"
    current_role = step.get("to_role") or role_fallback
    to_person = step_agent(step)
    summary = result.get("summary", "") or ""

    from lib.infra.utils import json_read as _json_read

    cfg = _json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else {}
    crt_rt = step_role_type(step)
    from lib.composition import run_step_verify, notify_verify_failure
    from lib.adapters.orchestration.automation import bump_retry_count, retry_exceeded, verify_fail_auto_retry

    v_ok, v_err, v_meta = run_step_verify(
        crt_rt, conclusion, result, config=cfg, data_dir=data_dir or "",
    )
    if not v_ok:
        attempt = bump_retry_count(task, "verify_fail")
        vc = (cfg.get("mailbus_automation") or {}).get("verify") or {}
        notify_verify_failure(
            data_dir or "",
            task_id=task.get("task_id") or task.get("id") or "",
            agent=to_person or "",
            role_label=current_role or "",
            reason=v_err or "verify_failed",
            attempt=attempt,
            escalate_cfg=vc.get("escalate_on_attempt") or {"2": "agent-m", "3": "agent-a"},
        )
        if verify_fail_auto_retry(task, cfg) and not retry_exceeded(task, cfg, key="verify_fail"):
            _append_history(task, "verify_failed", {
                "error": v_err, "step_id": step.get("step_id"), "attempt": attempt, "meta": v_meta,
            })
            return {
                "ok": False,
                "error": "verify_failed",
                "message": v_err,
                "action": "retry_same_step",
                "task": task,
            }
        task["fsm"]["state"] = TaskFsmState.BLOCKED.value
        _append_history(task, "verify_blocked", {"error": v_err, "attempt": attempt, "meta": v_meta})
        try:
            from lib.composition import build_orchestration

            build_orchestration(data_dir or "").notifier.notify(
                "verify_fail_blocked",
                {
                    "task_id": task.get("task_id") or task.get("id") or "",
                    "agent": to_person or "",
                    "attempt": attempt,
                    "reason": v_err,
                    "step_id": step.get("step_id"),
                },
            )
        except Exception:
            pass
        return {"ok": True, "action": "blocked", "task": task, "reason": v_err}

    report = {
        "conclusion": conclusion,
        "summary": summary,
        "template": "report",
        "details": result,
    }

    complete_step(step, report)
    _append_history(task, "submit", {
        "step_id": step.get("step_id"),
        "agent": to_person,
        "conclusion": conclusion,
    })

    if not data_dir:
        data_dir = os.path.join(PROJECT_ROOT_STR, "store")

    from lib.composition import block_for_clarifications, handle_design_step_decomposition

    dec_out = handle_design_step_decomposition(task, step, result, data_dir=data_dir)
    if dec_out:
        action = dec_out.get("action")
        if action in ("clarifications", "missing_decomposition", "invalid_decomposition"):
            reason = dec_out.get("reason") or ",".join(dec_out.get("errors") or [])
            block_for_clarifications(task, result, data_dir=data_dir, reason=reason or action)
            return {
                "ok": True,
                "action": "blocked",
                "task": task,
                "reason": action,
                "decomposition": dec_out,
            }
        if action == "subtasks_applied":
            _append_history(task, "decomposition_applied", {"count": dec_out.get("count")})

    from lib.composition import maybe_block_after_step

    wf_block = maybe_block_after_step(task, step, result, data_dir=data_dir)
    if wf_block:
        _append_history(task, "workflow_gate", wf_block)
        return {"ok": True, "action": "blocked", "task": task, "reason": wf_block.get("gate_id")}

    # ── P0-1：collab 并行组成员完成 → 组内等待 / 汇合 join ──────────────
    cj = step.get("collab_join") or {}
    if step.get("parallel_group") and cj:
        gid = step["parallel_group"]
        total = int(cj.get("total") or 0)
        terminal = {
            StepFsmState.COMPLETED.value,
            StepFsmState.SKIPPED.value,
            StepFsmState.SUPERSEDED.value,
        }
        done_cnt = 0
        failed_member = False
        pending_members = []
        for s in chain:
            if not (s.get("parallel_group") == gid):
                continue
            st = s.get("fsm_state") or s.get("status") or ""
            if st == StepFsmState.FAILED.value:
                failed_member = True
            elif st in terminal:
                done_cnt += 1
            else:
                pending_members.append(s)
        if failed_member:
            task["fsm"]["state"] = TaskFsmState.BLOCKED.value
            _append_history(task, "collab_member_failed", {
                "group": gid, "step_id": step.get("step_id"),
            })
            return {"ok": True, "action": "blocked", "task": task, "reason": "collab_member_failed"}
        if done_cnt < total:
            # 还有兄弟在跑：不推进，等待全部完成（active 指到最后一个待办成员）
            task["fsm"]["state"] = TaskFsmState.EXECUTING.value
            if pending_members:
                task["fsm"]["active_step_id"] = pending_members[-1].get("step_id")
            _append_history(task, "parallel_await", {
                "group": gid, "resolved": done_cnt, "total": total,
            })
            return {"ok": True, "action": "parallel_await", "task": task}

        gate = cj.get("join_gate") or "auto"
        if gate == "review":
            task["fsm"]["state"] = TaskFsmState.BLOCKED.value
            task["fsm"]["substate"] = "await_join_review"
            task["fsm"]["reason"] = "join_gate_review"
            task["fsm"]["join_pending"] = {
                "group": gid,
                "join_role_type": cj.get("join_role_type"),
                "join_gate": gate,
            }
            _append_history(task, "await_join_review", {"group": gid, "gate": gate})
            return {"ok": True, "action": "await_join_review", "task": task, "reason": "join_gate_review"}
        if gate != "auto":
            task["fsm"]["state"] = TaskFsmState.BLOCKED.value
            task["fsm"]["reason"] = "join_gate_not_supported"
            _append_history(task, "join_gate_not_supported", {"gate": gate})
            return {"ok": True, "action": "blocked", "task": task, "reason": "join_gate_not_supported"}

        return _advance_collab_join(
            task, step, chain, current_role, to_person, summary, cj, data_dir=data_dir,
        )

    n_role, n_person, kind = resolve_transition(
        chain, result, current_role, conclusion, agents, data_dir=data_dir,
    )

    next_role_type = None
    if kind == "advance" and is_role_pipeline_task(task) and n_role:
        from lib.adapters.locale.role_labels import zh_to_role_type
        next_role_type = result.get("next_role_type")
        if next_role_type is not None:
            try:
                next_role_type = int(next_role_type)
            except (TypeError, ValueError):
                next_role_type = zh_to_role_type(n_role, data_dir)
        else:
            next_role_type = zh_to_role_type(n_role, data_dir)

    if kind == "terminal":
        from lib.composition import enter_accepting_or_succeed

        outcome = enter_accepting_or_succeed(task, result, data_dir=data_dir)
        if outcome == "auto_accept":
            _append_history(task, "complete", {"reason": "auto_accept"})
            return {"ok": True, "action": "terminal", "task": task}
        _append_history(task, "complete", {"reason": "accepting"})
        return {"ok": True, "action": "accepting", "task": task}

    if kind == "blocked" and not n_role:
        task["fsm"]["state"] = TaskFsmState.BLOCKED.value
        _append_history(task, "blocked", {"conclusion": conclusion, "step_id": step.get("step_id")})
        return {"ok": True, "action": "blocked", "task": task, "reason": "no_next_assignee"}

    if not n_role or not n_person:
        task["fsm"]["state"] = TaskFsmState.BLOCKED.value
        return {"ok": False, "error": "no_assignee", "action": "blocked"}

    rollback_from = step.get("step_id") if kind == "rollback_flow" else None
    nxt = create_next_step(
        task,
        to_role=n_role,
        to_person=n_person,
        from_role=current_role,
        from_person=to_person,
        rollback_from=rollback_from,
        reason=summary[:200],
        role_type=next_role_type,
    )
    chain.append(nxt)
    task["assignee"] = n_person
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"]["active_step_id"] = nxt["step_id"]
    task["status"] = "running"
    _append_history(task, "advance", {
        "from_step": step.get("step_id"),
        "to_step": nxt["step_id"],
        "to_person": n_person,
        "kind": kind,
    })
    return {
        "ok": True,
        "action": "advance",
        "next_step": nxt,
        "next_person": n_person,
        "next_role": n_role,
        "task": task,
    }


def revert_failed_advance(task: dict, completed_step: dict, next_step: dict) -> None:
    """推送下一步失败时，撤销 apply_submit 产生的 advance。"""
    chain = task.get("chain") or []
    if chain and chain[-1].get("step_id") == next_step.get("step_id"):
        chain.pop()
    completed_step["status"] = "running"
    completed_step["fsm_state"] = StepFsmState.AWAITING_RESULT.value
    completed_step.pop("completed_at", None)
    completed_step.pop("report", None)
    completed_step["result_consumed"] = False
    ensure_fsm(task)
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"]["active_step_id"] = completed_step.get("step_id")
    task["assignee"] = completed_step.get("to_person", "")
    task["status"] = "running"


def apply_rollback(
    task: dict,
    *,
    to_step: Optional[int] = None,
    to_person: Optional[str] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """回退到指定 step 序号或 agent，追加重做步骤（保留历史）。"""
    ensure_fsm(task)
    chain = task.get("chain") or []
    active = get_active_step(task)
    if not active:
        return {"ok": False, "error": "no_active_step"}

    target = None
    if to_step is not None:
        for s in chain:
            if int(s.get("step") or 0) == int(to_step):
                target = s
                break
    elif to_person:
        for s in reversed(chain):
            if s.get("to_person") == to_person and s.get("fsm_state") == StepFsmState.COMPLETED.value:
                target = s
                break
    if not target:
        return {"ok": False, "error": "rollback_target_not_found"}

    fail_step(active, reason or "rollback")
    idx = chain.index(active)
    for s in chain[idx + 1:]:
        supersede_step(s)

    nxt = create_next_step(
        task,
        to_role=target.get("to_role", ""),
        to_person=target.get("to_person", ""),
        from_role=active.get("to_role", ""),
        from_person=active.get("to_person", ""),
        rollback_from=active.get("step_id"),
        reason=reason,
    )
    chain.append(nxt)
    task["assignee"] = nxt["to_person"]
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"]["active_step_id"] = nxt["step_id"]
    task["status"] = "running"
    _append_history(task, "rollback", {
        "to_step": target.get("step"),
        "to_person": target.get("to_person"),
        "reason": reason,
        "new_step_id": nxt["step_id"],
    })
    return {"ok": True, "action": "rollback", "next_step": nxt, "task": task}


def apply_skip(task: dict, reason: str = "") -> Dict[str, Any]:
    ensure_fsm(task)
    step = get_active_step(task)
    if not step:
        return {"ok": False, "error": "no_active_step"}
    step["fsm_state"] = StepFsmState.SKIPPED.value
    step["status"] = "skipped"
    step["completed_at"] = _now_iso()
    step["skip_reason"] = reason
    _append_history(task, "skip", {"step_id": step.get("step_id"), "reason": reason})
    return {"ok": True, "action": "skip", "task": task, "needs_manual_advance": True}


def apply_cancel(task: dict, reason: str = "", *, data_dir: str = "", agents: Optional[dict] = None) -> Dict[str, Any]:
    ensure_fsm(task)
    if data_dir:
        from lib.core.a2a.a2a_cancel import cancel_inflight_a2a_for_task

        cancel_inflight_a2a_for_task(data_dir, task, agents=agents, reason=reason)
    step = get_active_step(task)
    if step:
        step["fsm_state"] = StepFsmState.SUPERSEDED.value
    task["fsm"]["state"] = TaskFsmState.CANCELLED.value
    task["status"] = "cancelled"
    task["error"] = reason or "cancelled"
    _append_history(task, "cancel", {"reason": reason})
    return {"ok": True, "action": "cancel", "task": task}


def apply_pause(task: dict, reason: str = "") -> Dict[str, Any]:
    ensure_fsm(task)
    task["fsm"]["state"] = TaskFsmState.PAUSED.value
    task["status"] = "paused"
    task["pause_reason"] = reason
    _append_history(task, "pause", {"reason": reason})
    return {"ok": True, "action": "pause", "task": task}


def apply_resume(task: dict) -> Dict[str, Any]:
    """Resume a paused task into executing."""
    ensure_fsm(task)
    st = task.setdefault("fsm", {})
    if st.get("state") != TaskFsmState.PAUSED.value:
        return {"ok": True, "action": "noop", "task": task}
    st["state"] = TaskFsmState.EXECUTING.value
    task["status"] = "running"
    reason = task.pop("pause_reason", None)
    hist = st.setdefault("history", [])
    hist.append({"event": "resume", "reason": reason})
    return {"ok": True, "action": "resume", "task": task}


def bump_retry(task: dict, *, step_id: str = "") -> int:
    """Q7: retry counters live on task JSON."""
    ensure_fsm(task)
    st = task.setdefault("fsm", {})
    retries = st.setdefault("retries", {})
    key = step_id or "_task"
    n = int(retries.get(key) or 0) + 1
    retries[key] = n
    st["retry_total"] = int(st.get("retry_total") or 0) + 1
    if step_id:
        for step in task.get("chain") or []:
            if isinstance(step, dict) and step.get("step_id") == step_id:
                step["retry_count"] = n
                break
    return n


def fsm_summary(task: dict) -> dict:
    """API / Dashboard 用的状态机摘要。"""
    ensure_fsm(task)
    active = get_active_step(task)
    chain = task.get("chain") or []
    steps_view = []
    for s in chain:
        if not isinstance(s, dict):
            continue
        steps_view.append({
            "step": s.get("step"),
            "step_id": s.get("step_id"),
            "fsm_state": s.get("fsm_state"),
            "to_role": s.get("to_role"),
            "to_person": s.get("to_person"),
            "attempt": s.get("attempt", 1),
            "result_ref": s.get("result_ref"),
            "node_type": s.get("node_type") or "agent",
            "automation": s.get("automation") or (
                "human" if s.get("fsm_state") == "blocked" else "auto"
            ),
        })
    return {
        "task_id": task.get("task_id") or task.get("id"),
        "fsm_state": (task.get("fsm") or {}).get("state"),
        "priority": task_priority(task),
        "active_step_id": (task.get("fsm") or {}).get("active_step_id"),
        "active_step": {
            "step_id": active.get("step_id") if active else None,
            "fsm_state": active.get("fsm_state") if active else None,
            "to_person": active.get("to_person") if active else None,
        },
        "steps": steps_view,
    }


def list_executable_tasks(tasks: List[dict]) -> List[dict]:
    """按 priority 排序的可执行任务。"""
    running = [ensure_fsm(t) for t in tasks if is_task_executable(t)]
    return sorted(running, key=lambda t: (task_priority(t), t.get("created_at") or ""))
