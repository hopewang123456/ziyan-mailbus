"""pipeline_trigger.py — FSM 驱动的 pipeline 检测与推进

scan housekeeping 调用 trigger()：
1. 规范化 task FSM 状态
2. 读取 per-step / legacy msg-results
3. 通过 task_fsm.apply_submit 转移状态并 dispatch 下一步
"""

import os
from datetime import datetime, timezone

from .mbus_log import debug, info, warn
from .tracker import TaskTracker, _parse_iso_dt
from .pipeline_chain import normalize_task_chain, is_pipeline_step
from .pipeline_step import planned_agents_remaining, planned_role_types_remaining
from .models import Inbox
from .utils import json_read, json_write, _now_iso
from .task_fsm import (
    TaskFsmState,
    apply_submit,
    ensure_fsm,
    get_active_step,
    is_task_executable,
    mark_step_dispatched,
    read_step_result,
    result_applies_to_step,
    step_result_path,
    legacy_result_path,
    write_step_result,
)

TRUSTED_RESULT_SOURCES = (
    "validate-scheduler",
    "pipeline-e2e-regression",
    "mailbus-scheduler",
    "run-game-lvup-e2e",
)


def trigger(data_dir: str, agents: dict, paths: dict):
    """主入口：扫描所有任务链，检测结果文件并推进（FSM）。"""
    tra = TaskTracker(data_dir)
    for t in tra.list_all():
        _process_task_pipeline(t, data_dir, agents, paths, tra)


def trigger_task(data_dir: str, task_id: str, agents: dict, paths: dict) -> dict:
    """单任务即时推进（G-02）— 写 step result 后调用。"""
    tra = TaskTracker(data_dir)
    t = tra.get(task_id)
    if not t:
        return {"ok": False, "error": "not_found"}
    return _process_task_pipeline(t, data_dir, agents, paths, tra)


def _process_task_pipeline(t: dict, data_dir: str, agents: dict, paths: dict, tra: TaskTracker) -> dict:
    """处理单个 pipeline 任务的 result → apply_submit → dispatch。"""
    task_id = t.get("task_id", t.get("id", ""))
    task_file = os.path.join(tra.tasks_dir, "%s.json" % task_id)
    raw_chain = t.get("chain")
    t = normalize_task_chain(t)
    t = ensure_fsm(t)
    if t.get("chain") != raw_chain or t.get("fsm"):
        json_write(task_file, t)

    chain = t.get("chain", [])
    if not chain or not is_pipeline_step(chain[0]):
        return {"ok": True, "skipped": "not_pipeline"}

    fsm_state = (t.get("fsm") or {}).get("state", "")
    if fsm_state in (TaskFsmState.PAUSED.value, TaskFsmState.CANCELLED.value):
        return {"ok": True, "skipped": "paused_or_cancelled"}

    current = get_active_step(t)
    if not current:
        return {"ok": True, "skipped": "no_active_step"}

    status = current.get("status", "")
    fs = current.get("fsm_state", "")
    if status in ("completed", "done") or fs == "completed":
        all_done = all(
            s.get("status") in ("completed", "done", "skipped")
            or s.get("fsm_state") in ("completed", "skipped", "superseded")
            for s in chain if isinstance(s, dict)
        )
        if all_done and not planned_role_types_remaining(chain) and not planned_agents_remaining(chain) and t.get("status") != "success":
            fsm_st = (t.get("fsm") or {}).get("state", "")
            if fsm_st not in (TaskFsmState.SUCCEEDED.value, TaskFsmState.ACCEPTING.value):
                from .fsm_actions import enter_accepting_or_succeed

                enter_accepting_or_succeed(t, {}, data_dir=data_dir)
                json_write(task_file, t)
                info(f"[fsm] accepting {task_id[:30]}")
        return {"ok": True, "skipped": "step_completed"}

    if not is_task_executable(t):
        return {"ok": True, "skipped": "not_executable"}

    from .pipeline_step import step_agent
    to_person = step_agent(current)
    if not to_person:
        return {"ok": True, "skipped": "no_assignee"}

    if current.get("result_consumed"):
        return {"ok": True, "skipped": "result_consumed"}

    result = read_step_result(data_dir, task_id, current)
    if not result:
        return {"ok": True, "skipped": "no_result"}

    mtime_ok = _result_mtime_ok(data_dir, task_id, current, result)
    ok, reason = result_applies_to_step(
        result, task_id, current, chain, result_mtime_ok=mtime_ok,
    )
    if not ok:
        return {"ok": True, "skipped": reason or "result_not_applicable"}

    if current.get("to_role") == "审查官":
        from .audit_dispatch import sync_audit_from_result
        sync_audit_from_result(
            tra, t, result,
            reviewer=to_person,
            reviewer_role=current.get("to_role", ""),
        )

    sid = current.get("step_id")
    if sid and not os.path.isfile(step_result_path(data_dir, task_id, sid)):
        write_step_result(data_dir, task_id, current, result, immediate_advance=False)

    outcome = apply_submit(t, result, agents=agents, data_dir=data_dir)
    if not outcome.get("ok"):
        if outcome.get("action") == "retry_same_step":
            from .task_fsm import archive_step_result_for_retry
            archive_step_result_for_retry(data_dir, task_id, current, result)
            t = outcome.get("task") or t
            json_write(task_file, t)
            summary = result.get("summary", "") or outcome.get("message", "verify retry")
            if _send_task(
                data_dir, paths, to_person, current.get("to_role", ""),
                current.get("to_role", ""), to_person, summary, task_id,
                step_num=current.get("step") or len(chain),
                step_id=current.get("step_id"),
                result_ref=current.get("result_ref"),
            ):
                info(f"[fsm] verify retry redispatch {task_id[:24]} -> {to_person}")
                return {"ok": True, "action": "retry_same_step"}
            warn(f"[fsm] verify retry dispatch failed {task_id[:30]}")
        debug(f"[fsm] {task_id[:24]} submit rejected: {outcome.get('error')}")
        return {"ok": False, "error": outcome.get("error")}

    action = outcome.get("action")
    if action == "terminal":
        t["audit_reviewer"] = t.get("audit_reviewer") or "lingjian"
        json_write(task_file, t)
        from .audit_dispatch import backfill_audit_from_chain
        backfill_audit_from_chain(data_dir)
        _close_pipeline_inbox(data_dir, paths, task_id, agents)
        info(f"[fsm] succeeded {task_id[:30]}")
        return {"ok": True, "action": "terminal"}

    if action == "accepting":
        t["audit_reviewer"] = t.get("audit_reviewer") or "lingjian"
        json_write(task_file, t)
        info(f"[fsm] awaiting acceptance {task_id[:30]}")
        return {"ok": True, "action": "accepting"}

    if action == "blocked":
        json_write(task_file, t)
        debug(f"[fsm] blocked {task_id[:24]} conclusion={result.get('conclusion')}")
        return {"ok": True, "action": "blocked"}

    if action == "advance":
        nxt = outcome.get("next_step") or {}
        n_role = outcome.get("next_role", "")
        n_person = outcome.get("next_person", "")
        summary = result.get("summary", "") or ""
        info(
            f"[fsm] {task_id[:24]} step done -> {n_role}/{n_person} "
            f"next={nxt.get('step_id', '?')}"
        )

        if not _send_task(
            data_dir, paths, to_person, current.get("to_role", ""),
            n_role, n_person, summary, task_id,
            step_num=nxt.get("step") or len(chain),
            step_id=nxt.get("step_id"),
            result_ref=nxt.get("result_ref"),
        ):
            from .task_fsm import revert_failed_advance
            revert_failed_advance(t, current, nxt)
            json_write(task_file, t)
            warn(f"[fsm] dispatch failed rollback {task_id[:30]}")
            return {"ok": False, "error": "dispatch_failed"}

        mark_step_dispatched(nxt)
        t["assignee"] = n_person
        json_write(task_file, t)
        return {"ok": True, "action": "advance"}

    return {"ok": True, "action": action or "unknown"}


def trigger_legacy(data_dir: str, agents: dict, paths: dict):
    """兼容别名。"""
    trigger(data_dir, agents, paths)


def _result_mtime_ok(data_dir: str, task_id: str, current: dict, result: dict) -> bool:
    step_started = current.get("started_at") or ""
    result_ts = result.get("timestamp") or result.get("updated_at") or ""
    if step_started and result_ts:
        try:
            return _parse_iso_dt(result_ts) >= _parse_iso_dt(step_started)
        except Exception:
            return True
    if step_started:
        sid = current.get("step_id")
        paths_to_try = []
        if sid:
            paths_to_try.append(step_result_path(data_dir, task_id, sid))
        paths_to_try.append(legacy_result_path(data_dir, task_id))
        for rf in paths_to_try:
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(rf), tz=timezone.utc)
                return mtime >= _parse_iso_dt(step_started)
            except OSError:
                continue
    return True


def _close_pipeline_inbox(data_dir: str, paths: dict, task_id: str, agents: dict) -> int:
    """任务 success 后关闭各 agent inbox 中该 task 的 pending/pushed/processing 消息。"""
    from .models import MsgStatus

    closed = 0
    ts = _now_iso()
    tag = f"【{task_id}】"
    for name in agents:
        inbox_file = os.path.join(paths["inbox"], name, "inbox.json")
        if not os.path.isfile(inbox_file):
            continue
        data = json_read(inbox_file, {})
        if not data:
            continue
        inbox = Inbox.from_dict(data)
        changed = False
        for m_raw in inbox.messages:
            mid = inbox.msg_field(m_raw, "id", "")
            content = inbox.msg_field(m_raw, "content", "")
            state = inbox.msg_field(m_raw, "state", "") or inbox.msg_field(m_raw, "status", "")
            if tag not in content:
                continue
            if state in (MsgStatus.DONE, MsgStatus.CLOSED):
                continue
            inbox.set_msg_status(
                mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                done_at=ts, done_note=f"auto: pipeline success {task_id}",
            )
            closed += 1
            changed = True
        if changed:
            json_write(inbox_file, inbox.to_dict())
    if closed:
        debug(f"[fsm] closed {closed} inbox msgs {task_id[:24]}")
    return closed


def _send_task(
    data_dir, paths, from_person, from_role, to_role, to_person,
    summary, task_id="", step_num=1, step_id=None, result_ref=None,
):
    """写任务文件和推送消息给下一步的 agent。成功返回 True。"""
    from .pipeline_work_order import write_pipeline_work_order

    task_path = os.path.join(data_dir, "tasks", f"{task_id}.json")
    planned = None
    planned_rt = None
    if os.path.isfile(task_path):
        tdata = json_read(task_path, {})
        chain = tdata.get("chain") or []
        if chain:
            head = chain[0]
            planned = head.get("planned_agents")
            planned_rt = head.get("planned_role_types")

    nid, nf = write_pipeline_work_order(
        data_dir,
        task_id=task_id,
        step_num=step_num,
        to_person=to_person,
        to_role=to_role,
        from_person=from_person,
        from_role=from_role,
        summary=summary,
        planned_agents=planned,
        planned_role_types=planned_rt,
        step_id=step_id,
    )
    if result_ref:
        rf = os.path.join(data_dir, result_ref.replace("/mailbus/store/", "").lstrip("/"))
    elif step_id:
        rf = step_result_path(data_dir, task_id, step_id)
    else:
        rf = legacy_result_path(data_dir, task_id)

    nxt_file = os.path.join(paths["inbox"], to_person, "inbox.json")
    if not os.path.exists(os.path.dirname(nxt_file)):
        return False

    nxt_data = json_read(nxt_file, {})
    nxt_inbox = Inbox.from_dict(nxt_data) if nxt_data else Inbox(agent=to_person)
    step_hint = f"step_id={step_id}" if step_id else f"pipeline_step={step_num}"
    nxt_inbox.messages.append({
        "id": nid,
        "from": from_person,
        "to": to_person,
        "type": "task",
        "priority": "normal",
        "state": "pending",
        "task_id": task_id,
        "content": (
            "📋 【%s】pipeline 步骤 (%s)\n任务文件: %s\n结果写入: %s\n"
            "请读取任务文件执行，完成后写结果文件（含 pipeline_step 与 step_id）。\n\n"
            "⚠️ 必须写入结果文件才能完成。"
        ) % (task_id, step_hint, nf, rf),
        "created_at": _now_iso(),
    })
    nxt_inbox.has_unread = True
    json_write(nxt_file, nxt_inbox.to_dict())
    debug(f"[fsm] pushed {to_person} task={task_id[:24]} {step_hint}")
    return True


# ── 兼容旧测试 / 工具 ─────────────────────────────────────────────────────

def _find_result(data_dir, task_id):
    """legacy: 精确 msg-results/{task_id}.json"""
    p = legacy_result_path(data_dir, task_id)
    return p if os.path.isfile(p) else None


def _result_applies_to_step(result: dict, result_file: str, task_id: str, current: dict, chain: list) -> bool:
    step_started = current.get("started_at") or ""
    result_ts = result.get("timestamp") or result.get("updated_at") or ""
    mtime_ok = True
    if step_started and result_ts:
        try:
            mtime_ok = _parse_iso_dt(result_ts) >= _parse_iso_dt(step_started)
        except Exception:
            mtime_ok = True
    elif step_started and result_file and os.path.isfile(result_file):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(result_file), tz=timezone.utc)
            mtime_ok = mtime >= _parse_iso_dt(step_started)
        except (OSError, Exception):
            pass
    ok, _ = result_applies_to_step(result, task_id, current, chain, result_mtime_ok=mtime_ok)
    return ok


def _is_done(result):
    from .task_fsm import _DONE_CONCLUSIONS
    c = (result.get("conclusion") or "").lower()
    if c in _DONE_CONCLUSIONS:
        return True
    return result.get("status") == "completed"
