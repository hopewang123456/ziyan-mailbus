"""Workflow gate API — POST /api/tasks/{id}/gates/{gate_id}/approve|deny。"""

from __future__ import annotations

import os

from lib.tracker import TaskTracker
from lib.utils import json_write
from lib.workflow.engine import on_gate_approve, on_gate_deny


def _save_task(data_dir: str, task: dict) -> None:
    tid = task.get("task_id") or task.get("id") or ""
    json_write(os.path.join(data_dir, "tasks", f"{tid}.json"), task)


def handle_gate_approve(handler, task_id: str, gate_id: str):
    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return

    body = handler._read_post_body()
    outcome = on_gate_approve(handler.data_dir, task, gate_id, body)
    if not outcome.get("ok"):
        handler._send_json({"status": "error", **outcome}, outcome.get("http", 400))
        return

    _save_task(handler.data_dir, task)
    handler._send_json({
        "status": "ok",
        "gate_id": gate_id,
        "resolution": outcome.get("resolution"),
        "actions": outcome.get("actions", []),
        "dispatch_ok": outcome.get("dispatch_ok"),
        "task": {
            "task_id": task_id,
            "fsm": task.get("fsm"),
            "extensions": task.get("extensions"),
        },
        "human_queue": {"status": "approved"},
    })


def handle_gate_deny(handler, task_id: str, gate_id: str):
    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return

    body = handler._read_post_body()
    outcome = on_gate_deny(handler.data_dir, task, gate_id, body)
    if not outcome.get("ok"):
        handler._send_json({"status": "error", **outcome}, outcome.get("http", 400))
        return

    _save_task(handler.data_dir, task)
    handler._send_json({
        "status": "ok",
        "gate_id": gate_id,
        "resolution": outcome.get("resolution"),
        "actions": outcome.get("actions", []),
        "task": {
            "task_id": task_id,
            "fsm": task.get("fsm"),
            "extensions": task.get("extensions"),
        },
    })
