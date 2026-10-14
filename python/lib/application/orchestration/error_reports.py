"""error_report 扫描 + tracker 状态更新 — application 层编排。

原位置 `lib/adapters/results/ack_handler.scan_error_reports`（2026-09 治理下沉）。
adapter→application 跨层违规修正：扫描 inbox 的纯 I/O 任务仍然在 adapter，
但「扫描 + 调 TaskTracker 更新任务失败状态」这条业务编排链搬到 application 层。

adapter 只剩一个 thin wrapper，调用本模块的服务函数。
"""
from __future__ import annotations

from typing import List, Dict, Any

from lib.infra.utils import json_read, resolve_paths, _now_iso
from lib.infra.mbus_log import warn
from lib.domain.models import Inbox
from lib.application.orchestration.tracker import TaskTracker, TaskStatus


def _collect_error_reports(data_dir: str, agents: dict) -> List[Dict[str, Any]]:
    """扫描所有 inbox 中的 error_report 消息，返回 raw 列表（不含 tracker 更新）。"""
    paths = resolve_paths(data_dir)
    reports: List[Dict[str, Any]] = []

    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue

        inbox = Inbox.from_dict(inbox_data)
        for m in inbox.messages:
            msg_type = inbox.msg_field(m, "type", "")
            task_id = inbox.msg_field(m, "task_id", "")
            error = inbox.msg_field(m, "error", {})

            if msg_type == "error_report" and error and task_id:
                reports.append({
                    "task_id": task_id,
                    "agent": name,
                    "error": error,
                })

    return reports


def scan_and_apply_error_reports(data_dir: str, agents: dict) -> list:
    """扫描 error_report 并把对应任务状态更新为 failed。

    返回结构: [{task_id, agent, error_code, reason}]。
    失败更新不影响其他记录的处理（单条 try/except 隔离）。
    """
    raw = _collect_error_reports(data_dir, agents)
    out: List[Dict[str, Any]] = []

    for r in raw:
        task_id = r["task_id"]
        agent = r["agent"]
        error = r["error"]
        try:
            tracker = TaskTracker(data_dir)
            tracker.update_status(task_id, TaskStatus.FAILED, error={
                "code": error.get("code", "UNKNOWN"),
                "reason": error.get("reason", ""),
                "detail": error.get("trace", ""),
                "agent": agent,
                "reported_at": _now_iso(),
            })
        except Exception as e:
            warn(f"[error_reports] tracker update failed for {task_id}: {e}")
        out.append({
            "task_id": task_id,
            "agent": agent,
            "error_code": error.get("code", "UNKNOWN"),
            "reason": error.get("reason", ""),
        })

    return out


__all__ = ["scan_and_apply_error_reports"]