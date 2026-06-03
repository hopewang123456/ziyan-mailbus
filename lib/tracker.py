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
        """列出所有任务，可选按状态过滤"""
        if not os.path.isdir(self.tasks_dir):
            return []
        results = []
        for fname in sorted(os.listdir(self.tasks_dir)):
            if fname.endswith(".json"):
                task = json_read(os.path.join(self.tasks_dir, fname), None)
                if task and (not status_filter or task.get("status") == status_filter):
                    results.append(task)
        return results

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
