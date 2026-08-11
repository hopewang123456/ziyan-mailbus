"""POST /api/tasks/<id>/gates/<gate_id>/{approve|deny}."""

from __future__ import annotations

from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_write
from lib.application.workflow.engine import on_gate_approve, on_gate_deny


def handle_gate_approve(handler, task_id: str, gate_id: str):
    body = handler._read_post_body()
    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"ok": False, "error": "not_found"}, 404)
        return
    outcome = on_gate_approve(handler.data_dir, task, gate_id, body or {})
    if outcome.get("ok"):
        json_write(tracker._task_path(task_id), task)
    status = int(outcome.pop("http", 200 if outcome.get("ok") else 400))
    handler._send_json(outcome, status)


def handle_gate_deny(handler, task_id: str, gate_id: str):
    body = handler._read_post_body()
    tracker = TaskTracker(handler.data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"ok": False, "error": "not_found"}, 404)
        return
    outcome = on_gate_deny(handler.data_dir, task, gate_id, body or {})
    if outcome.get("ok"):
        json_write(tracker._task_path(task_id), task)
    status = int(outcome.pop("http", 200 if outcome.get("ok") else 400))
    handler._send_json(outcome, status)
