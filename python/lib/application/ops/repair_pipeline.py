"""Ops: repair stuck pipeline tasks (Wave5 · tools 业务下沉)."""
from __future__ import annotations

import json
import os
from typing import Any

from lib.domain.models import Inbox
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_read, json_write


def report_stuck_pipeline(data_dir: str, task_id: str) -> dict[str, Any]:
    tr = TaskTracker(data_dir)
    task = tr.get(task_id) or {}
    mr = os.path.join(data_dir, "msg-results", f"{task_id}.json")
    out: dict[str, Any] = {
        "task_id": task_id,
        "status": task.get("status"),
        "assignee": task.get("assignee"),
        "has_msg_results": os.path.isfile(mr),
        "duplicate_trackers": [],
        "stale_queues": [],
        "phantom_replies": [],
        "inbox_missing_task": False,
    }

    for t in tr.list_all():
        tid = t.get("task_id", "")
        if tid.startswith("msg-") and task_id in (t.get("summary") or ""):
            out["duplicate_trackers"].append({"task_id": tid, "status": t.get("status")})

    assignee = (task.get("chain") or [{}])[-1].get("to_person") or task.get("assignee", "")
    if assignee:
        qf = os.path.join(data_dir, "queue", "urgent", f"{assignee}.json")
        if os.path.isfile(qf):
            out["stale_queues"].append(qf)

        inbox_file = os.path.join(data_dir, "inbox", assignee, "inbox.json")
        inbox_data = json_read(inbox_file, {})
        has_task_msg = False
        if inbox_data:
            inbox = Inbox.from_dict(inbox_data)
            for m in inbox.messages:
                c = inbox.msg_field(m, "content", "")
                tid_f = inbox.msg_field(m, "task_id", "")
                if task_id in c or tid_f == task_id:
                    has_task_msg = True
                    break
        out["inbox_missing_task"] = not has_task_msg

    replies_file = os.path.join(data_dir, "replies", f"{assignee}.json")
    rep = json_read(replies_file, {})
    if rep and task_id in json.dumps(rep, ensure_ascii=False):
        if not os.path.isfile(mr):
            out["phantom_replies"].append(replies_file)

    return out


def fix_stuck_pipeline(data_dir: str, task_id: str) -> dict[str, Any]:
    tr = TaskTracker(data_dir)
    cancelled = []
    for t in tr.list_all():
        tid = t.get("task_id", "")
        if tid.startswith("msg-") and task_id in (t.get("summary") or ""):
            tr.update_status(tid, "cancelled", error={"reason": "repair: duplicate msg-* tracker"})
            cancelled.append(tid)

    task = tr.get(task_id) or {}
    assignee = (task.get("chain") or [{}])[-1].get("to_person") or task.get("assignee", "")
    removed_queue = False
    cleared_reply = False
    if assignee:
        qf = os.path.join(data_dir, "queue", "urgent", f"{assignee}.json")
        if os.path.isfile(qf):
            os.remove(qf)
            removed_queue = True
        rf = os.path.join(data_dir, "replies", f"{assignee}.json")
        if os.path.isfile(rf) and not os.path.isfile(os.path.join(data_dir, "msg-results", f"{task_id}.json")):
            json_write(rf, {})
            cleared_reply = True
    return {
        "ok": True,
        "cancelled_trackers": cancelled,
        "removed_queue": removed_queue,
        "cleared_phantom_reply": cleared_reply,
    }
