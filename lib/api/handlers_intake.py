"""GET/POST /api/intake — 商前 intake API。"""

from __future__ import annotations

from lib.application.workflow.intake.gates import on_intake_gate_approve, on_intake_gate_deny
from lib.application.workflow.intake.spawn_rules import load_bridge_config
from lib.application.workflow.intake.store import get, load_all
from lib.application.workflow.intake.task_bridge import spawn_analyze, spawn_by_kinds
from lib.application.orchestration.tracker import TaskTracker


def handle_intake_list(handler):
    items = load_all(handler.data_dir)
    handler._send_json({"status": "ok", "intakes": items, "count": len(items)})


def handle_intake_get(handler, intake_id: str):
    intake = get(handler.data_dir, intake_id)
    if not intake:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return
    handler._send_json({"status": "ok", "intake": intake})


def handle_intake_tasks(handler, intake_id: str):
    intake = get(handler.data_dir, intake_id)
    if not intake:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return
    link = intake.get("pipeline_link") or {}
    tr = TaskTracker(handler.data_dir)
    tasks = []
    for key in ("intake_task_id", "solution_task_id", "content_task_id"):
        tid = link.get(key)
        if not tid:
            continue
        task = tr.get(tid)
        if task:
            tasks.append({"link_key": key, "task_id": tid, "task": task})
    handler._send_json({"status": "ok", "intake_id": intake_id, "tasks": tasks})


def handle_intake_spawn_analyze(handler):
    body = handler._read_post_body()
    intake_id = (body.get("intake_id") or "").strip()
    if not intake_id:
        handler._send_json({"status": "error", "error": "intake_id required"}, 400)
        return
    cfg = load_bridge_config(handler.data_dir)
    if not cfg.get("enabled", True):
        handler._send_json({"status": "error", "error": "bridge_disabled"}, 409)
        return
    out = spawn_analyze(handler.data_dir, intake_id, force=bool(body.get("force")))
    handler._send_json({"status": "ok", **out}, 201)


def handle_intake_spawn(handler, intake_id: str):
    body = handler._read_post_body()
    kinds = body.get("kinds") or []
    if not kinds:
        handler._send_json({"status": "error", "error": "kinds required"}, 400)
        return
    try:
        out = spawn_by_kinds(handler.data_dir, intake_id, kinds)
    except Exception as exc:
        code = getattr(exc, "code", "spawn_failed")
        handler._send_json({"status": "error", "error": code, "message": str(exc)}, 409)
        return
    handler._send_json({"status": "ok", "intake_id": intake_id, **out}, 201)


def handle_intake_gate_approve(handler, intake_id: str, gate_id: str):
    body = handler._read_post_body()
    outcome = on_intake_gate_approve(handler.data_dir, intake_id, gate_id, body)
    status = int(outcome.pop("http", 200 if outcome.get("ok") else 400))
    handler._send_json(outcome, status)


def handle_intake_gate_deny(handler, intake_id: str, gate_id: str):
    body = handler._read_post_body()
    outcome = on_intake_gate_deny(handler.data_dir, intake_id, gate_id, body)
    status = int(outcome.pop("http", 200 if outcome.get("ok") else 400))
    handler._send_json(outcome, status)
