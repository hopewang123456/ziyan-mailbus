"""Step result 远程回写 API — POST /api/agents/{agent_id}/step-result"""

from __future__ import annotations

import os

from lib.tracker import TaskTracker
from lib.pipeline_step import step_agent
from lib.task_fsm import (
    ensure_fsm,
    get_active_step,
    write_step_result,
)
from lib.utils import json_read


_REQUIRED = ("task_id", "step_id", "agent", "role_type", "conclusion", "summary", "timestamp")


def handle_agent_step_result(handler, agent_id: str) -> None:
    body = handler._read_post_body()
    if not isinstance(body, dict):
        handler._send_json({"status": "error", "error": "invalid_body"}, 400)
        return

    missing = [k for k in _REQUIRED if not body.get(k) and body.get(k) != 0]
    if missing:
        handler._send_json({
            "status": "error",
            "error": "schema_invalid",
            "details": [f"missing {k}" for k in missing],
        }, 400)
        return

    if (body.get("agent") or "").lower() != agent_id.lower():
        handler._send_json({
            "status": "error",
            "error": "agent_mismatch",
            "message": "body.agent must match path agent_id",
        }, 403)
        return

    task_id = body["task_id"]
    data_dir = handler.data_dir
    tracker = TaskTracker(data_dir)
    task = tracker.get(task_id)
    if not task:
        handler._send_json({"status": "error", "error": "task_not_found"}, 404)
        return

    task = ensure_fsm(task)
    active = get_active_step(task)
    if not active:
        handler._send_json({"status": "error", "error": "no_active_step"}, 409)
        return

    if body.get("step_id") != active.get("step_id"):
        handler._send_json({
            "status": "error",
            "error": "wrong_step",
            "expected_step_id": active.get("step_id"),
        }, 409)
        return

    expected = step_agent(active) or active.get("to_person") or ""
    if expected and body.get("agent") != expected:
        handler._send_json({
            "status": "error",
            "error": "wrong_agent",
            "expected_agent": expected,
        }, 403)
        return

    path = write_step_result(data_dir, task_id, active, body)
    rel = path.replace("\\", "/")
    if data_dir.replace("\\", "/") in rel:
        rel = "msg-results/" + rel.split("msg-results/", 1)[-1]

    handler._send_json({
        "status": "ok",
        "path": rel,
        "task_id": task_id,
        "step_id": active.get("step_id"),
    })
