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


# ── 任务状态 ──────────────────────────────────────────────────────────

class TaskStatus:
    PENDING  = "pending"
    RUNNING  = "running"
    SUCCESS  = "success"
    FAILED   = "failed"
    TIMEOUT  = "timeout"
    CANCELLED = "cancelled"
    ALL = {PENDING, RUNNING, SUCCESS, FAILED, TIMEOUT, CANCELLED}


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
               deliverable: str = "", chain_hops: list = None) -> dict:
        """创建新任务"""
        task = {
            "task_id": task_id,
            "summary": summary,
            "assignee": assignee,
            "status": TaskStatus.PENDING,
            "deliverable": deliverable,
            "chain": chain_hops or [],
            "error": None,
            "reminded_count": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
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
                        reminder_minutes: int = 5,
                        max_reminders: int = 3) -> list:
        """
        检查所有 running 任务是否需要催办。
        
        如果传入了 data_dir，还会检查 inbox 中对应消息的状态，
        如果 inbox 中消息已 done，自动同步 tracker 状态。

        返回需要升级通知的任务列表 [{task_id, agent, reminded_count}, ...]
        """
        escalated = []
        now = datetime.now(timezone(timedelta(hours=8)))

        # 如果传了 data_dir，预加载所有 inbox 的消息状态
        msg_states = {}  # task_id -> inbox_state
        if data_dir:
            from .utils import resolve_paths
            from .models import Inbox
            paths = resolve_paths(data_dir)
            for name in agents:
                inbox_file = f"{paths['inbox']}/{name}/inbox.json"
                inbox_data = json_read(inbox_file, {})
                if inbox_data:
                    inbox = Inbox.from_dict(inbox_data)
                    for m in inbox.messages:
                        mid = inbox.msg_field(m, 'id', '')
                        state = inbox.msg_field(m, 'state', '') or inbox.msg_field(m, 'status', '')
                        if mid and state:
                            msg_states[mid] = state

        for task in self.list_all(status_filter=TaskStatus.RUNNING):
            task_id = task["task_id"]
            
            # 检查 inbox 中对应消息是否已 done
            inbox_state = msg_states.get(task_id, "")
            if inbox_state in ("done", "closed", "acknowledged"):
                self.update_status(task_id, TaskStatus.SUCCESS)
                continue
            
            updated_str = task.get("updated_at", task["created_at"])
            updated = datetime.strptime(updated_str, "%Y-%m-%dT%H:%M:%S%z")
            elapsed_min = (now - updated).total_seconds() / 60

            if elapsed_min >= reminder_minutes and task["reminded_count"] < max_reminders:
                # 需要催办
                self.increment_reminder(task_id)
                assignee = task.get("assignee", "")
                if assignee in agents:
                    escalated.append({
                        "task_id": task_id,
                        "agent": assignee,
                        "summary": task.get("summary", ""),
                        "reminded_count": task["reminded_count"],
                    })
            elif elapsed_min >= reminder_minutes and task["reminded_count"] >= max_reminders:
                # 超限 → 标记 timeout
                self.update_status(task_id, TaskStatus.TIMEOUT)

        return escalated

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
                pending.append(task)
        pending.sort(
            key=lambda t: _parse_iso_dt(t.get("updated_at", t.get("created_at", ""))),
            reverse=True,
        )
        return pending[:limit]
