"""ziyan-mailbus 任务追踪器

管理 store/tasks/ 目录，提供任务的创建、状态更新、催办、链追踪。"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from .models import MsgStatus, _now_iso
from .utils import json_read, json_write, jsonl_append, resolve_paths, log_error
from lib.adapters.clock import now_dt
from lib.application.orchestration.pipeline.chain import (
    init_pipeline_chain,
    is_pipeline_step,
    normalize_task_chain,
)

# 不参与 tracker 超时判定的 task_id 前缀（系统通知/催办噪音）
SKIP_TIMEOUT_PREFIXES = (
    "remind-", "tracker-remind-", "patrol-", "heartbeat-",
    "confirm-", "rule-change-", "alert-task-",
)

# inbox 消息「进行中」态 — 有 agent 在处理时不应判 timeout
INBOX_ACTIVE_STATES = frozenset({
    "processing", "acknowledged", "pushed", "running", "in_progress",
})

# inbox 终态 — 对应 tracker success
INBOX_DONE_STATES = frozenset({
    "done", "closed", "sent", "archived",
})


# ── 任务状态 ──────────────────────────────────────────────────────────

class TaskStatus:
    PENDING  = "pending"
    RUNNING  = "running"
    PAUSED   = "paused"
    SUCCESS  = "success"
    FAILED   = "failed"
    TIMEOUT  = "timeout"
    CANCELLED = "cancelled"
    ALL = {PENDING, RUNNING, PAUSED, SUCCESS, FAILED, TIMEOUT, CANCELLED}


# ── 追踪链状态 ────────────────────────────────────────────────────────

class ChainStatus:
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    ALL = {IN_PROGRESS, COMPLETED, FAILED}


def _parse_iso_dt(s: str) -> datetime:
    """安全解析 ISO 时间字符串（带或不带时区），返回 timezone-aware datetime。

    支持格式：
      - 2026-06-03T15:12:58+0800
      - 2026-06-03T15:12:58
    解析失败时返回 epoch (UTC) 作为 fallback，确保排序不崩溃。
    """
    if not s:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        pass
    try:
        # 无时区 → 视为 UTC
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


class TaskTracker:
    """任务追踪器"""

    def __init__(self, data_dir: str):
        self.tasks_dir = os.path.join(data_dir, "tasks")
        os.makedirs(self.tasks_dir, exist_ok=True)

    def _task_path(self, task_id: str) -> str:
        return os.path.join(self.tasks_dir, f"{task_id}.json")

    def create(self, task_id: str, summary: str = "", assignee: str = "",
               deliverable: str = "", chain_hops: list = None,
               requires_audit: bool = None, priority: int = 50) -> dict:
        """创建新任务"""
        from .audit_dispatch import infer_requires_audit
        from lib.adapters.orchestration.task_fsm import ensure_fsm

        pipeline_chain = init_pipeline_chain(chain_hops, assignee, task_id)
        req_audit = infer_requires_audit(task_id, chain_hops, requires_audit, pipeline_chain)
        task = {
            "task_id": task_id,
            "summary": summary,
            "assignee": assignee or (pipeline_chain[0].get("to_agent") or pipeline_chain[0].get("to_person") if pipeline_chain else ""),
            "status": "running" if pipeline_chain else TaskStatus.PENDING,
            "deliverable": deliverable,
            "chain": pipeline_chain,
            "requires_audit": req_audit,
            "error": None,
            "reminded_count": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        if req_audit:
            task["audit_reviewer"] = "lingjian"
        ensure_fsm(task, default_priority=int(priority))
        json_write(self._task_path(task_id), task)
        return task

    def create_from_envelope(
        self,
        envelope: dict,
        *,
        planned_chain: list,
        plan_meta: dict,
    ) -> dict:
        """v3 Envelope 落盘。"""
        from .audit_dispatch import infer_requires_audit
        from lib.application.orchestration.dispatch.role_resolver import resolve_agent_for_role_type
        from lib.application.orchestration.dispatch.tier_filter import dispatch_action_from_envelope, dispatch_action_from_step
        from lib.application.orchestration.pipeline.chain import init_chain_from_planned
        from lib.adapters.orchestration.task_fsm import TaskFsmState, ensure_fsm

        task_id = envelope["task_id"]
        priority = int((envelope.get("fsm") or {}).get("priority", 50))
        data_root = os.path.dirname(self.tasks_dir)
        agents_cfg = json_read(os.path.join(data_root, "config.json"), {}).get("agents") or {}
        env_action = dispatch_action_from_envelope(envelope)

        def _resolve(rt, pin, planned_item=None):
            step_action = dispatch_action_from_step(planned_item or {}, envelope)
            merged = {**env_action, **step_action}
            return resolve_agent_for_role_type(
                data_root, rt, pin_agent=pin, action=merged, agents_cfg=agents_cfg,
            )

        pipeline_chain = init_chain_from_planned(
            planned_chain,
            task_id,
            resolve_agent=_resolve,
        )

        intent = envelope.get("intent") or ""
        first_agent = pipeline_chain[0].get("to_agent") or ""

        task = {
            "task_id": task_id,
            "protocol_version": envelope.get("protocol_version", "mailbus-a2a/1"),
            "intent": intent,
            "summary": intent[:120],
            "initiator": envelope.get("initiator", "human"),
            "mode": envelope.get("mode"),
            "tier": envelope.get("tier"),
            "task_type": envelope.get("task_type"),
            "assignee": first_agent,
            "status": "pending",
            "chain": pipeline_chain,
            "extensions": envelope.get("extensions") or {},
            "constraints": envelope.get("constraints") or {},
            "acceptance": envelope.get("acceptance") or {},
            "artifacts_in": envelope.get("artifacts_in") or [],
            "plan_meta": plan_meta,
            "requires_audit": infer_requires_audit(
                task_id, None, None, pipeline_chain,
            ),
            "error": None,
            "reminded_count": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        if task["requires_audit"]:
            task["audit_reviewer"] = "lingjian"

        ensure_fsm(task, default_priority=priority)
        fsm = task["fsm"]
        sub = (envelope.get("fsm") or {}).get("substate")
        if sub:
            fsm["substate"] = sub
        if fsm.get("state") == TaskFsmState.EXECUTING.value:
            task["status"] = "running"
        elif fsm.get("state") == TaskFsmState.CREATED.value:
            task["status"] = "pending"

        json_write(self._task_path(task_id), task)
        return task

    def get(self, task_id: str) -> Optional[dict]:
        return json_read(self._task_path(task_id), None)

    def update_status(self, task_id: str, status: str, error: dict = None):
        """更新任务状态"""
        task = self.get(task_id)
        if not task:
            return None
        task["status"] = status
        task["updated_at"] = _now_iso()
        if error:
            task["error"] = error
        json_write(self._task_path(task_id), task)
        return task

    def add_hop(self, task_id: str, agent: str, action: str):
        """追加追踪链一跳"""
        task = self.get(task_id)
        if not task:
            return None
        task["chain"].append({
            "agent": agent,
            "action": action,
            "status": "done",
            "at": _now_iso(),
        })
        task["updated_at"] = _now_iso()
        json_write(self._task_path(task_id), task)
        return task

    def increment_reminder(self, task_id: str) -> int:
        """增加催办次数，返回当前催办次数"""
        task = self.get(task_id)
        if not task:
            return 0
        task["reminded_count"] += 1
        task["updated_at"] = _now_iso()
        json_write(self._task_path(task_id), task)
        return task["reminded_count"]

    def list_all(self, status_filter: str = None) -> list:
        """列出所有任务，可选按状态过滤，按 updated_at 倒序（最新的在最上面）"""
        if not os.path.isdir(self.tasks_dir):
            return []
        results = []
        for fname in os.listdir(self.tasks_dir):
            if fname.endswith(".json"):
                task = json_read(os.path.join(self.tasks_dir, fname), None)
                if task and (not status_filter or task.get("status") == status_filter):
                    results.append(task)
        # 按 updated_at 倒序（最新的在最上面），fallback 到 created_at
        # 使用 _parse_iso_dt 安全解析带时区后缀（如 +0800）的时间字符串
        results.sort(key=lambda t: _parse_iso_dt(t.get("updated_at", t.get("created_at", ""))), reverse=True)
        return results

    def list_by_filters(self, status: str = None, assignee: str = None,
                        audit_status: str = None, reviewer: str = None,
                        limit: int = 100, offset: int = 0) -> dict:
        """按多条件过滤任务列表，支持分页

        Args:
            status: 任务状态过滤
            assignee: 负责人过滤
            audit_status: 审计状态 (audited / pending-audit / all)
            reviewer: 审查人过滤（仅匹配 audit_log 中存在的审查人）
            limit: 每页数量
            offset: 偏移量

        Returns:
            {"tasks": [...], "total": int, "limit": int, "offset": int}
        """
        all_tasks = self.list_all()
        filtered = []

        for task in all_tasks:
            # 状态过滤
            if status and (task.get("status") or "").lower() != status.lower():
                continue

            # 负责人过滤
            if assignee and (task.get("assignee") or "").lower() != assignee.lower():
                continue

            # 审计状态过滤
            has_audit = bool(task.get("audit_log"))
            if audit_status == "audited" and not has_audit:
                continue
            if audit_status == "pending-audit":
                term_statuses = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT}
                if task.get("status") not in term_statuses or has_audit:
                    continue
                from .audit_dispatch import task_requires_audit
                if not task_requires_audit(task):
                    continue

            # 审查人过滤
            if reviewer:
                audit_log = task.get("audit_log", [])
                if not any(e.get("reviewer") == reviewer for e in audit_log):
                    continue

            filtered.append(task)

        total = len(filtered)
        paged = filtered[offset:offset + limit]

        return {
            "tasks": paged,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def add_audit(self, task_id: str, reviewer: str, result: str,
                  issues: list = None, summary: str = "", report_file: str = "",
                  category: str = "", severity: str = "normal",
                  affected_components: list = None):
        """追加审计记录到任务

        Args:
            task_id: 任务 ID
            reviewer: 审查人
            result: pass / fail / warn
            issues: 问题列表，每个元素可为 dict {desc, severity, file, line}
            summary: 审计摘要
            report_file: 关联的报告文件路径
            category: 审计类别 (code_review / design / security / performance / other)
            severity: 严重级别 (critical / high / normal / low)
            affected_components: 影响的组件列表
        """
        task = self.get(task_id)
        if not task:
            return None
        if "audit_log" not in task:
            task["audit_log"] = []
        # 审计轮次
        round_num = len(task["audit_log"]) + 1
        entry = {
            "reviewer": reviewer,
            "result": result,
            "issues": issues or [],
            "summary": summary,
            "report_file": report_file,
            "category": category,
            "severity": severity,
            "affected_components": affected_components or [],
            "round": round_num,
            "at": _now_iso(),
        }
        task["audit_log"].append(entry)
        task["updated_at"] = _now_iso()
        # 如果审计失败，自动标记任务为 failed
        if result == "fail":
            task["status"] = TaskStatus.FAILED
        json_write(self._task_path(task_id), task)
        return task

    # ── 催办逻辑 ──────────────────────────────────────────────────

    def check_reminders(self, agents: dict, data_dir: str = None,
                        reminder_minutes: int = 30,
                        max_reminders: int = 12) -> list:
        """
        检查所有 running 任务是否需要催办。
        
        如果传入了 data_dir，还会检查 inbox 中对应消息的状态，
        如果 inbox 中消息已 done，自动同步 tracker 状态。

        返回需要升级通知的任务列表 [{task_id, agent, reminded_count}, ...]
        """
        import re
        escalated = []
        now = now_dt()

        msg_states = {}   # msg_id -> state
        task_states = {}  # 逻辑 task_id -> state
        if data_dir:
            from .models import Inbox
            paths = resolve_paths(data_dir)
            bracket_re = re.compile(r"【([^】]{4,120})】")
            for name in agents:
                inbox_file = f"{paths['inbox']}/{name}/inbox.json"
                inbox_data = json_read(inbox_file, {})
                if not inbox_data:
                    continue
                inbox = Inbox.from_dict(inbox_data)
                for m in inbox.messages:
                    mid = inbox.msg_field(m, 'id', '')
                    state = (inbox.msg_field(m, 'state', '')
                             or inbox.msg_field(m, 'status', '')).lower()
                    if not mid:
                        continue
                    msg_states[mid] = state
                    for key in (inbox.msg_field(m, 'task_id', ''), mid):
                        if key:
                            task_states[key] = self._pick_better_state(
                                task_states.get(key), state)
                    content = inbox.msg_field(m, 'content', '') or ''
                    for match in bracket_re.finditer(content):
                        tid = match.group(1).strip()
                        if tid:
                            task_states[tid] = self._pick_better_state(
                                task_states.get(tid), state)

        for task in self.list_all(status_filter=TaskStatus.RUNNING):
            task_id = task["task_id"]

            if self._skip_timeout(task_id, task):
                continue

            # 已有 msg-results → 等 pipeline_trigger 推进，不判 timeout
            if data_dir and self._has_msg_result(data_dir, task_id):
                continue

            inbox_state = task_states.get(task_id, msg_states.get(task_id, ""))
            if not inbox_state:
                chain = task.get("chain") or []
                if chain and isinstance(chain[0], dict):
                    step_tid = chain[0].get("task_id", "")
                    if step_tid:
                        inbox_state = task_states.get(step_tid, "")

            if inbox_state in INBOX_DONE_STATES:
                from .audit_dispatch import task_requires_audit
                from lib.application.orchestration.pipeline.chain import is_pipeline_step
                chain = task.get("chain") or []
                multi_step = len(chain) > 1 or (
                    chain and isinstance(chain[0], dict) and chain[0].get("planned_agents")
                )
                if multi_step or (task_requires_audit(task) and not task.get("audit_log")):
                    continue
                self.update_status(task_id, TaskStatus.SUCCESS)
                continue

            if inbox_state in INBOX_ACTIVE_STATES:
                # agent 已 ack/处理中 — 重置催办计数，给足执行时间
                if task.get("reminded_count", 0) > 0:
                    task["reminded_count"] = 0
                    task["updated_at"] = _now_iso()
                    json_write(self._task_path(task_id), task)
                continue

            updated_str = task.get("updated_at", task.get("created_at", ""))
            updated = _parse_iso_dt(updated_str)
            elapsed_min = (now - updated).total_seconds() / 60

            if elapsed_min >= reminder_minutes and task["reminded_count"] < max_reminders:
                count = self.increment_reminder(task_id)
                assignee = task.get("assignee", "")
                if assignee in agents:
                    escalated.append({
                        "task_id": task_id,
                        "agent": assignee,
                        "summary": task.get("summary", ""),
                        "reminded_count": count,
                    })
            elif elapsed_min >= reminder_minutes and task["reminded_count"] >= max_reminders:
                chain = task.get("chain") or []
                if chain:
                    from lib.application.orchestration.pipeline.chain import is_pipeline_step
                    from lib.adapters.orchestration.task_fsm import get_active_step
                    if is_pipeline_step(chain[0]) or chain[0].get("planned_agents"):
                        active = get_active_step(task)
                        if active and active.get("status") == "running":
                            continue
                self.update_status(task_id, TaskStatus.TIMEOUT, error={
                    "code": "TIMEOUT",
                    "reason": f"超过{max_reminders}次催办（间隔{reminder_minutes}分钟）未响应",
                })

        return escalated

    @staticmethod
    def _pick_better_state(old: str, new: str) -> str:
        """合并同一 task 的多条 inbox 消息状态，取更「进展」的一个。"""
        rank = {
            "": 0, "new": 1, "pending": 1, "sent": 2, "received": 2,
            "pushed": 3, "acknowledged": 4, "processing": 5, "running": 5,
            "in_progress": 5, "done": 10, "closed": 10, "archived": 10,
            "failed": 9, "rejected": 9,
        }
        if rank.get(new, 0) >= rank.get(old or "", 0):
            return new
        return old or new

    @staticmethod
    def _skip_timeout(task_id: str, task: dict) -> bool:
        if any(task_id.startswith(p) for p in SKIP_TIMEOUT_PREFIXES):
            return True
        summary = (task.get("summary") or "")[:80]
        if summary.startswith("⚠️ 超时提醒") or summary.startswith("⏰ 催办提醒"):
            return True
        return False

    @staticmethod
    def _has_msg_result(data_dir: str, task_id: str) -> bool:
        return os.path.isfile(os.path.join(data_dir, "msg-results", f"{task_id}.json"))

    def reopen_stale_timeouts(self, agents: dict, data_dir: str) -> int:
        """恢复误标 timeout 的 pipeline 任务（inbox 仍在 pending/processing 时）。"""
        import re
        paths = resolve_paths(data_dir)
        from .models import Inbox
        task_states = {}
        bracket_re = re.compile(r"【([^】]{4,120})】")
        for name in agents:
            inbox_data = json_read(f"{paths['inbox']}/{name}/inbox.json", {})
            if not inbox_data:
                continue
            inbox = Inbox.from_dict(inbox_data)
            for m in inbox.messages:
                mid = inbox.msg_field(m, 'id', '')
                state = (inbox.msg_field(m, 'state', '')
                         or inbox.msg_field(m, 'status', '')).lower()
                if not mid:
                    continue
                for key in (inbox.msg_field(m, 'task_id', ''), mid):
                    if key:
                        task_states[key] = self._pick_better_state(
                            task_states.get(key), state)
                content = inbox.msg_field(m, 'content', '') or ''
                for match in bracket_re.finditer(content):
                    tid = match.group(1).strip()
                    if tid:
                        task_states[tid] = self._pick_better_state(
                            task_states.get(tid), state)

        reopened = 0
        for task in self.list_all(status_filter=TaskStatus.TIMEOUT):
            task_id = task.get("task_id", "")
            if self._skip_timeout(task_id, task):
                continue
            chain = task.get("chain") or []
            if not chain:
                continue
            is_pipeline = is_pipeline_step(chain[0]) or chain[0].get("planned_agents")
            if not is_pipeline:
                continue
            state = task_states.get(task_id, "")
            if not state and chain[0].get("task_id"):
                state = task_states.get(chain[0]["task_id"], "")
            if state in INBOX_DONE_STATES or self._has_msg_result(data_dir, task_id):
                continue
            if state in INBOX_ACTIVE_STATES or state in ("", "pending", "sent", "new", "received"):
                task["status"] = TaskStatus.RUNNING
                task["reminded_count"] = 0
                task["error"] = None
                task["updated_at"] = _now_iso()
                json_write(self._task_path(task_id), task)
                reopened += 1
        return reopened

    # ── 审计趋势 ──────────────────────────────────────────────────

    def audit_trend(self, period: str = "day", days: int = 30) -> dict:
        """获取审计趋势（按日/周/月聚合）

        Args:
            period: 聚合周期 (day / week / month)
            days: 回溯天数（默认 30 天）

        Returns:
            {
                "trend": [{"period": "2026-06-01", "total": 10, "pass": 8, ...}, ...],
                "summary": {"total_audits": ..., "avg_pass_rate": ...}
            }
        """
        all_tasks = self.list_all()
        from collections import defaultdict

        # 收集所有审计记录，按 at 时间归类
        raw_entries = []  # [(period_key, result), ...]
        for task in all_tasks:
            audit_log = task.get("audit_log", [])
            for entry in audit_log:
                at_str = entry.get("at", "")
                if not at_str:
                    continue
                result = entry.get("result", "")
                period_key = self._truncate_to_period(at_str, period)
                if period_key:
                    raw_entries.append((period_key, result))

        if not raw_entries:
            return {"trend": [], "summary": {"total_audits": 0, "avg_pass_rate": 0.0}}

        # 按 period_key 聚合
        agg = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "warn": 0})
        for pk, result in raw_entries:
            agg[pk]["total"] += 1
            if result in agg[pk]:
                agg[pk][result] += 1

        # 计算 pass_rate
        trend = []
        total_all = 0
        total_pass = 0
        for pk in sorted(agg.keys()):
            a = agg[pk]
            pr = round(a["pass"] / a["total"] * 100, 1) if a["total"] > 0 else 0.0
            trend.append({
                "period": pk,
                "total": a["total"],
                "pass": a["pass"],
                "fail": a["fail"],
                "warn": a["warn"],
                "pass_rate": pr,
            })
            total_all += a["total"]
            total_pass += a["pass"]

        avg_rate = round(total_pass / total_all * 100, 1) if total_all > 0 else 0.0

        return {
            "trend": trend,
            "summary": {
                "total_audits": total_all,
                "avg_pass_rate": avg_rate,
                "period": period,
                "days": days,
            },
        }

    @staticmethod
    def _truncate_to_period(iso_str: str, period: str) -> str:
        """将 ISO 时间字符串截断到指定周期

        支持格式: 2026-06-03T15:12:58+0800 或 2026-06-03T15:12:58
        返回:
            day:   "2026-06-03"
            week:  "2026-W23"
            month: "2026-06"
        """
        if not iso_str:
            return ""
        # 提取日期部分
        date_part = iso_str[:10]  # "2026-06-03"
        if period == "day":
            return date_part
        try:
            from datetime import datetime
            dt = datetime.strptime(date_part, "%Y-%m-%d")
            if period == "week":
                iso_cal = dt.isocalendar()
                return f"{iso_cal[0]}-W{iso_cal[1]:02d}"
            elif period == "month":
                return date_part[:7]
        except (ValueError, ImportError):
            pass
        return date_part

    # ── 审计统计 ──────────────────────────────────────────────────

    def audit_stats(self) -> dict:
        """获取审计聚合统计

        Returns:
            {
                "total_tasks": int,
                "audited_tasks": int,
                "pending_audit_tasks": int,
                "pass_count": int,
                "fail_count": int,
                "warn_count": int,
                "by_reviewer": {reviewer: {pass, fail, warn, total}},
                "by_category": {category: count},
                "by_severity": {severity: count},
                "latest_audits": [{task_id, summary, result, reviewer, at}, ...]
            }
        """
        all_tasks = self.list_all()
        stats = {
            "total_tasks": len(all_tasks),
            "audited_tasks": 0,
            "pending_audit_tasks": 0,
            "pass_count": 0,
            "fail_count": 0,
            "warn_count": 0,
            "by_reviewer": {},
            "by_category": {},
            "by_severity": {},
            "latest_audits": [],
        }

        for task in all_tasks:
            audit_log = task.get("audit_log", [])
            if audit_log:
                stats["audited_tasks"] += 1
                for entry in audit_log:
                    result = entry.get("result", "")
                    if result == "pass":
                        stats["pass_count"] += 1
                    elif result == "fail":
                        stats["fail_count"] += 1
                    elif result == "warn":
                        stats["warn_count"] += 1

                    reviewer = entry.get("reviewer", "unknown")
                    if reviewer not in stats["by_reviewer"]:
                        stats["by_reviewer"][reviewer] = {"pass": 0, "fail": 0, "warn": 0, "total": 0}
                    stats["by_reviewer"][reviewer][result] = stats["by_reviewer"][reviewer].get(result, 0) + 1
                    stats["by_reviewer"][reviewer]["total"] += 1

                    cat = entry.get("category", "") or "other"
                    stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1

                    sev = entry.get("severity", "normal")
                    stats["by_severity"][sev] = stats["by_severity"].get(sev, 0) + 1

                    stats["latest_audits"].append({
                        "task_id": task.get("task_id", ""),
                        "summary": (task.get("summary", "") or "")[:60],
                        "result": result,
                        "reviewer": reviewer,
                        "at": entry.get("at", ""),
                    })
            else:
                status = (task.get("status", "") or "").lower()
                if status in ("success", "failed", "timeout"):
                    from .audit_dispatch import task_requires_audit
                    if task_requires_audit(task):
                        stats["pending_audit_tasks"] += 1

        # 最新审计记录按时间倒序
        stats["latest_audits"].sort(key=lambda x: x.get("at", ""), reverse=True)
        stats["latest_audits"] = stats["latest_audits"][:20]

        # 审计通过率
        total_audits = stats["pass_count"] + stats["fail_count"] + stats["warn_count"]
        stats["pass_rate"] = round(stats["pass_count"] / total_audits * 100, 1) if total_audits > 0 else 0.0
        stats["total_audit_entries"] = total_audits

        return stats

    def list_pending_audit(self, limit: int = 50) -> list:
        """列出待审计任务（有终结态但缺少审计记录的任务）

        Args:
            limit: 最大返回数量

        Returns:
            任务列表，按 updated_at 倒序
        """
        terminal_statuses = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT}
        pending = []
        for task in self.list_all():
            if task.get("status") in terminal_statuses and not task.get("audit_log"):
                from .audit_dispatch import task_requires_audit
                if task_requires_audit(task):
                    pending.append(task)
        pending.sort(
            key=lambda t: _parse_iso_dt(t.get("updated_at", t.get("created_at", ""))),
            reverse=True,
        )
        return pending[:limit]
