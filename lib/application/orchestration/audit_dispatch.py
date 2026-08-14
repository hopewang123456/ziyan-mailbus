"""审计策略：仅根 pipeline 任务需要 audit_log；审查官步骤完成时自动入库。"""

import os
from typing import List, Optional

from lib.infra.clock import now_dt, now_ts, now_utc_dt
from .tracker import TaskTracker, TaskStatus, SKIP_TIMEOUT_PREFIXES
from lib.application.orchestration.pipeline.chain import is_pipeline_step
from lib.domain.models import Inbox
from lib.infra.utils import json_read, json_write, _now_iso
from lib.infra.mbus_log import debug

AUDIT_REVIEWER = "agent-a"  # demo 默认审查人；真实名册从 org_defaults 读取
REVIEWER_ROLE = "审查官"
TERMINAL = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT}
MAX_DISPATCH_PER_SCAN = 2


def _reviewer(data_dir: str = "") -> str:
    """默认审查人 — org_defaults.reviewer（store config 可覆盖）。"""
    from lib.infra.org_defaults import org_default

    return org_default(data_dir, "reviewer", fallback=AUDIT_REVIEWER)

# 永不进入「待审计」的 task_id 前缀（消息投递 tracker ≠ pipeline 根任务）
NO_AUDIT_PREFIXES = (
    "msg-",
    "game-lvup-",
    "smoke-",
    "test-",
    "pipeline-",
) + SKIP_TIMEOUT_PREFIXES

_CONCLUSION_TO_AUDIT = {
    "pass": "pass",
    "fail": "fail",
    "done": "warn",
    "approved": "pass",
    "rejected": "fail",
}


def _is_noise_task(task_id: str, summary: str = "") -> bool:
    if any(task_id.startswith(p) for p in SKIP_TIMEOUT_PREFIXES):
        return True
    s = (summary or "")[:80]
    return s.startswith("⚠️ 超时提醒") or s.startswith("⏰ 催办提醒")


def infer_requires_audit(
    task_id: str,
    chain_hops=None,
    explicit: Optional[bool] = None,
    pipeline_chain: Optional[list] = None,
) -> bool:
    """创建任务时推断是否需要 audit_log。"""
    if explicit is not None:
        return bool(explicit)
    if any(task_id.startswith(p) for p in NO_AUDIT_PREFIXES):
        return False

    def _chain_needs_audit(chain: list) -> bool:
        return bool(
            chain
            and isinstance(chain[0], dict)
            and (is_pipeline_step(chain[0]) or chain[0].get("planned_agents"))
        )

    if pipeline_chain is not None and _chain_needs_audit(pipeline_chain):
        return True
    if chain_hops is not None:
        from lib.application.orchestration.pipeline.chain import init_pipeline_chain

        chain = init_pipeline_chain(chain_hops, "", task_id)
        if _chain_needs_audit(chain):
            return True
    return False


def task_requires_audit(task: dict) -> bool:
    """Dashboard / gate 与 pending 列表统一口径。"""
    if task.get("requires_audit") is False:
        return False
    if task.get("requires_audit") is True:
        return True
    tid = task.get("task_id", "")
    if any(tid.startswith(p) for p in NO_AUDIT_PREFIXES):
        return False
    if _is_noise_task(tid, task.get("summary", "")):
        return False
    chain = task.get("chain") or []
    if not chain or not isinstance(chain[0], dict):
        return False
    if not (is_pipeline_step(chain[0]) or chain[0].get("planned_agents")):
        return False
    return True


# 兼容旧名
_needs_audit = task_requires_audit


def _reviewer_step_in_chain(task: dict) -> Optional[dict]:
    for step in task.get("chain") or []:
        if not isinstance(step, dict):
            continue
        if step.get("to_role") == REVIEWER_ROLE and step.get("status") in ("completed", "done"):
            return step
    return None


def sync_audit_from_result(
    tracker: TaskTracker,
    task: dict,
    result: dict,
    *,
    reviewer: str = "",
    reviewer_role: str = "",
) -> bool:
    """审查官（或显式 audit 字段）的 msg-results → audit_log。"""
    tid = task.get("task_id", "")
    if not tid or task.get("audit_log"):
        return False
    role = reviewer_role or result.get("role") or result.get("from_role") or ""
    person = reviewer or result.get("reviewer") or result.get("agent") or ""
    is_reviewer = role == REVIEWER_ROLE or person == AUDIT_REVIEWER
    is_explicit = bool(result.get("audit") or result.get("result") in ("pass", "fail", "warn"))
    if not is_reviewer and not is_explicit:
        return False
    conclusion = (result.get("conclusion") or result.get("result") or "done").lower()
    if conclusion in ("pass", "fail", "warn"):
        audit_result = conclusion
    else:
        audit_result = _CONCLUSION_TO_AUDIT.get(conclusion, "warn")
    summary = (
        result.get("summary")
        or (result.get("result") if isinstance(result.get("result"), str) else "")
        or result.get("message", "")
    )
    tracker.add_audit(
        task_id=tid,
        reviewer=person or AUDIT_REVIEWER,
        result=audit_result,
        issues=result.get("issues") or [],
        summary=str(summary)[:2000],
        category=result.get("category", "code_review"),
    )
    _mark_audit_inbox_done_from_tracker(tracker, tid)
    return True


def _sync_audit_from_step(tracker: TaskTracker, task: dict, step: dict) -> bool:
    report = step.get("report") or {}
    payload = report.get("details") if isinstance(report.get("details"), dict) else report
    if not isinstance(payload, dict):
        payload = {"summary": str(report.get("summary", "")), "conclusion": report.get("conclusion", "done")}
    payload.setdefault("summary", report.get("summary", ""))
    payload.setdefault("conclusion", report.get("conclusion", "done"))
    return sync_audit_from_result(
        tracker,
        task,
        payload,
        reviewer=step.get("to_person", AUDIT_REVIEWER),
        reviewer_role=step.get("to_role", REVIEWER_ROLE),
    )


def backfill_audit_from_chain(data_dir: str) -> int:
    """已完成的审查官 chain 步骤 / msg-results → 补写 audit_log（修复历史漏写）。"""
    tracker = TaskTracker(data_dir)
    filled = 0
    for task in tracker.list_all():
        if task.get("audit_log") or not task_requires_audit(task):
            continue
        step = _reviewer_step_in_chain(task)
        if step and _sync_audit_from_step(tracker, task, step):
            filled += 1
            debug(f"[audit] backfill reviewer step: {task.get('task_id')}")
            continue
        tid = task.get("task_id", "")
        rf = os.path.join(data_dir, "msg-results", f"{tid}.json")
        if os.path.isfile(rf):
            data = json_read(rf, {})
            if sync_audit_from_result(tracker, task, data):
                filled += 1
                debug(f"[audit] backfill msg-results: {tid}")
    return filled


def list_pending_audit_tasks(data_dir: str, limit: int = 50) -> List[dict]:
    tracker = TaskTracker(data_dir)
    out = []
    for task in tracker.list_all():
        if task.get("status") not in TERMINAL:
            continue
        if task.get("audit_log"):
            continue
        if not task_requires_audit(task):
            continue
        out.append(task)
    out.sort(
        key=lambda t: t.get("updated_at", t.get("created_at", "")),
        reverse=True,
    )
    return out[:limit]


def _audit_inbox_stale(inbox: Inbox, msg_id: str, *, hours: float = 6.0) -> bool:
    """审计 agent 的 audit-req 长期未 done 则允许重派。"""
    from datetime import datetime, timezone
    from .tracker import _parse_iso_dt

    for m in inbox.messages:
        if inbox.msg_field(m, "id", "") != msg_id:
            continue
        state = inbox.msg_field(m, "state", "")
        if state in ("done", "archived"):
            return False
        created = inbox.msg_field(m, "created_at", "") or ""
        if not created:
            return True
        try:
            age_h = (now_utc_dt() - _parse_iso_dt(created)).total_seconds() / 3600
            return age_h >= hours
        except Exception:
            return True
    return False


def _needs_redispatch(task: dict, inbox: Inbox, msg_id: str) -> bool:
    if not task.get("audit_dispatched_at"):
        return True
    if not any(inbox.msg_field(m, "id", "") == msg_id for m in inbox.messages):
        return True
    return _audit_inbox_stale(inbox, msg_id)


def _should_dispatch_side_audit(task: dict) -> bool:
    """仅对需要审计、且 pipeline 内尚无审查官结论的根任务派发 audit-req。"""
    if not task_requires_audit(task) or task.get("audit_log"):
        return False
    if _reviewer_step_in_chain(task):
        return False
    return True


def dispatch_pending_audits(data_dir: str, agents: dict, paths: dict) -> int:
    """Round1 主任务等：pipeline 未经过审查官步骤时，派单给默认审查人（每轮最多 2 条）。"""
    reviewer = _reviewer(data_dir)
    if reviewer not in agents:
        return 0

    from lib.application.orchestration.pipeline.task import side_audit_deferred_for_reviewer

    if side_audit_deferred_for_reviewer(data_dir, reviewer):
        debug(
            f"[audit] defer side-audit: primary pipeline assignee is {reviewer}"
        )
        return 0

    tracker = TaskTracker(data_dir)
    pending = [
        t for t in list_pending_audit_tasks(data_dir, 100)
        if _should_dispatch_side_audit(t)
    ]
    if not pending:
        return 0

    try:
        from .iteration_engine import load_iteration_state

        primary = load_iteration_state(data_dir).get("primary_task_id", "")
        if primary:
            primary_tasks = [t for t in pending if t.get("task_id") == primary]
            other = [t for t in pending if t.get("task_id") != primary]
            other.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
            pending = primary_tasks + other
    except Exception:
        pass

    inbox_file = f"{paths['inbox']}/{reviewer}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    inbox = Inbox.from_dict(inbox_data) if inbox_data else Inbox(agent=reviewer)

    dispatched = 0
    for task in pending[:MAX_DISPATCH_PER_SCAN]:
        tid = task["task_id"]
        status = task.get("status", "?")
        summary = (task.get("summary") or "")[:120]
        msg_id = f"audit-req-{tid}"[:80]
        if not _needs_redispatch(task, inbox, msg_id):
            continue

        existing = any(inbox.msg_field(m, "id", "") == msg_id for m in inbox.messages)
        if existing:
            if _audit_inbox_stale(inbox, msg_id):
                for m in inbox.messages:
                    if inbox.msg_field(m, "id", "") == msg_id:
                        if hasattr(m, "state"):
                            m.state = "pending"
                        elif isinstance(m, dict):
                            m["state"] = "pending"
                            m["created_at"] = _now_iso()
            task["audit_dispatched_at"] = task.get("audit_dispatched_at") or _now_iso()
            json_write(tracker._task_path(tid), task)
            continue

        content = f"""【audit:{tid}】请审计以下任务（Round1 门禁）

任务 ID: {tid}
终态: {status}
摘要: {summary}

请 POST /api/tasks/audit 或写 store/msg-results/audit-{tid}.json
（pipeline 审查官步骤的结论会自动入库，无需重复审计）"""

        inbox.messages.append({
            "id": msg_id,
            "from": "mailbus",
            "to": reviewer,
            "type": "task",
            "priority": "urgent",
            "state": "pending",
            "content": content,
            "created_at": _now_iso(),
            "action": {"ack": True, "execute": True, "store_memory": False},
        })
        inbox.has_unread = True
        task["audit_dispatched_at"] = _now_iso()
        task["audit_reviewer"] = reviewer
        json_write(tracker._task_path(tid), task)
        dispatched += 1

    if dispatched:
        json_write(inbox_file, inbox.to_dict())
        debug(f"[audit] dispatched {dispatched} pending -> {reviewer}")
    return dispatched


def submit_audit_result(
    data_dir: str,
    task_id: str,
    *,
    reviewer: str = "",
    result: str = "warn",
    summary: str = "",
    issues: list | None = None,
    category: str = "code_review",
    mark_inbox_done: bool = True,
) -> bool:
    """显式提交审计（API / 回归脚本）。"""
    reviewer = reviewer or _reviewer(data_dir)
    if result not in ("pass", "fail", "warn"):
        result = "warn"
    tracker = TaskTracker(data_dir)
    task = tracker.get(task_id)
    if not task:
        return False
    if task.get("audit_log"):
        return True
    payload = {
        "audit": True,
        "task_id": task_id,
        "reviewer": reviewer,
        "result": result,
        "summary": summary,
        "issues": issues or [],
    }
    audit_path = os.path.join(data_dir, "msg-results", f"audit-{task_id}.json")
    json_write(audit_path, {**payload, "agent": reviewer, "timestamp": _now_iso()})
    consume_audit_results(data_dir)
    if not tracker.get(task_id).get("audit_log"):
        tracker.add_audit(
            task_id=task_id,
            reviewer=reviewer,
            result=result,
            issues=payload["issues"],
            summary=summary,
            category=category,
        )
    if mark_inbox_done:
        _mark_audit_inbox_done(data_dir, task_id)
    return bool(tracker.get(task_id) and tracker.get(task_id).get("audit_log"))


def _mark_audit_inbox_done(data_dir: str, task_id: str) -> None:
    from lib.infra.utils import resolve_paths

    reviewer = _reviewer(data_dir)
    msg_id = f"audit-req-{task_id}"[:80]
    inbox_file = os.path.join(resolve_paths(data_dir)["inbox"], reviewer, "inbox.json")
    data = json_read(inbox_file, {})
    if not data:
        return
    inbox = Inbox.from_dict(data) if isinstance(data, dict) else None
    if not inbox:
        return
    changed = False
    for m in inbox.messages:
        mid = inbox.msg_field(m, "id", "")
        state = inbox.msg_field(m, "state", "")
        if mid == msg_id and state not in ("done", "archived"):
            if hasattr(m, "state"):
                m.state = "done"
                if hasattr(m, "status"):
                    m.status = "completed"
            elif isinstance(m, dict):
                m["state"] = "done"
                m["status"] = "completed"
            changed = True
    if changed:
        json_write(inbox_file, inbox.to_dict())


def _mark_audit_inbox_done_from_tracker(tracker: TaskTracker, task_id: str) -> None:
    data_dir = os.path.dirname(tracker.tasks_dir)
    _mark_audit_inbox_done(data_dir, task_id)


def reconcile_pending_audits(data_dir: str) -> dict:
    """scan 入口：consume 文件 → 审查官步骤补写 → 返回统计。"""
    out = {
        "consumed": consume_audit_results(data_dir),
        "backfilled": backfill_audit_from_chain(data_dir),
    }
    return out


def consume_audit_results(data_dir: str) -> int:
    """读取 msg-results/audit-*.json 并写入 tracker.audit_log。"""
    results_dir = os.path.join(data_dir, "msg-results")
    if not os.path.isdir(results_dir):
        return 0

    tracker = TaskTracker(data_dir)
    consumed = 0
    for fname in os.listdir(results_dir):
        if not fname.startswith("audit-") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(results_dir, fname)
        data = json_read(fpath, {})
        if not data.get("audit") and data.get("result") not in ("pass", "fail", "warn"):
            continue
        tid = data.get("task_id") or fname[6:-5]
        if not tid:
            continue
        task = tracker.get(tid)
        if not task or task.get("audit_log"):
            continue
        reviewer = data.get("agent") or data.get("reviewer") or ""
        if reviewer != _reviewer(data_dir):
            continue
        result = data.get("result", "warn")
        if result not in ("pass", "fail", "warn"):
            result = "warn"
        tracker.add_audit(
            task_id=tid,
            reviewer=reviewer or _reviewer(data_dir),
            result=result,
            issues=data.get("issues") or [],
            summary=data.get("summary", "") or data.get("message", ""),
            category=data.get("category", "code_review"),
            severity=data.get("severity", "normal"),
        )
        consumed += 1
        debug(f"[audit] consumed {tid} -> {result}")

    return consumed
