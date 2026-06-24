"""GET/POST /api/intake/* — 商前 intake REST。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from lib.intake.gates import on_intake_gate_approve, on_intake_gate_deny
from lib.intake.store import get, list_summaries
from lib.intake.task_bridge import spawn_analyze, spawn_by_kinds, SpawnError
from lib.tracker import TaskTracker


def _parse_qs(handler) -> dict:
    parsed = urlparse(handler.path)
    return parse_qs(parsed.query or "")


def handle_intake_list(handler):
    qs = _parse_qs(handler)
    decision = (qs.get("decision") or [""])[0]
    stage = (qs.get("stage") or [""])[0]
    try:
        limit = int((qs.get("limit") or ["50"])[0])
        offset = int((qs.get("offset") or ["0"])[0])
    except ValueError:
        handler._send_json({"error": "invalid limit/offset"}, 400)
        return
    items, total = list_summaries(
        handler.data_dir, decision=decision, stage=stage, limit=limit, offset=offset,
    )
    handler._send_json({"status": "ok", "total": total, "items": items})


def handle_intake_get(handler, intake_id: str):
    item = get(handler.data_dir, intake_id)
    if not item:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return
    handler._send_json({"status": "ok", "intake": item})


def handle_intake_tasks(handler, intake_id: str):
    item = get(handler.data_dir, intake_id)
    if not item:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return
    link = item.get("pipeline_link") or {}
    tracker = TaskTracker(handler.data_dir)
    tasks = []
    for key in ("intake_task_id", "solution_task_id", "content_task_id"):
        tid = link.get(key)
        if not tid:
            continue
        t = tracker.get(tid)
        if t:
            tasks.append({
                "role": key,
                "task_id": tid,
                "status": t.get("status"),
                "fsm": t.get("fsm"),
                "assignee": t.get("assignee"),
            })
    handler._send_json({"status": "ok", "intake_id": intake_id, "tasks": tasks})


def handle_intake_spawn(handler, intake_id: str):
    body = handler._read_post_body()
    kinds = body.get("kinds") or []
    if not isinstance(kinds, list) or not kinds:
        handler._send_json({"error": "missing_kinds"}, 400)
        return
    tier = body.get("tier") or "M"
    try:
        out = spawn_by_kinds(handler.data_dir, intake_id, kinds, tier=tier)
        handler._send_json({"status": "ok", **out}, 201 if out.get("spawned") else 200)
    except SpawnError as exc:
        code_map = {
            "not_found": 404,
            "gate_not_approved": 400,
            "invalid_kind": 400,
            "missing_kinds": 400,
            "task_exists": 409,
        }
        handler._send_json(
            {"status": "error", "error": exc.code, "message": str(exc)},
            code_map.get(exc.code, 400),
        )


def handle_intake_spawn_analyze(handler):
    body = handler._read_post_body()
    intake_id = body.get("intake_id", "")
    if not intake_id:
        handler._send_json({"error": "missing intake_id"}, 400)
        return
    try:
        out = spawn_analyze(handler.data_dir, intake_id, force=bool(body.get("force")))
        handler._send_json({"status": "ok", **out}, 201)
    except SpawnError as exc:
        code = 409 if exc.code == "already_spawned" else 404
        handler._send_json({"status": "error", "error": exc.code, "message": str(exc)}, code)


def handle_intake_gate_approve(handler, intake_id: str, gate_id: str):
    body = handler._read_post_body()
    outcome = on_intake_gate_approve(handler.data_dir, intake_id, gate_id, body)
    if not outcome.get("ok"):
        handler._send_json({"status": "error", **outcome}, outcome.get("http", 400))
        return
    handler._send_json({"status": "ok", **{k: v for k, v in outcome.items() if k != "http"}})


def handle_intake_gate_deny(handler, intake_id: str, gate_id: str):
    body = handler._read_post_body()
    outcome = on_intake_gate_deny(handler.data_dir, intake_id, gate_id, body)
    if not outcome.get("ok"):
        handler._send_json({"status": "error", **outcome}, outcome.get("http", 400))
        return
    handler._send_json({"status": "ok", **outcome})
