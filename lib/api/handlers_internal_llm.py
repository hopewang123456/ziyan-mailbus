"""POST/GET /api/internal-llm/* — Tier-1 Planner 调试与状态。"""

from __future__ import annotations

from lib.internal_llm.planner_llm import dry_run, load_llm_config
from lib.internal_llm.probe import probe_all
from lib.internal_llm.rag.index import rebuild_index
from lib.internal_llm.status import llm_status
from lib.router.planner import PlanError


def handle_internal_llm_status(handler):
    handler._send_json({"status": "ok", **llm_status(handler.data_dir)})


def handle_internal_llm_health(handler):
    handler._send_json({"status": "ok", **probe_all(handler.data_dir)})


def handle_internal_llm_dry_run(handler):
    body = handler._read_post_body()
    intent = body.get("intent") or ""
    if not intent:
        handler._send_json({"error": "missing intent"}, 400)
        return
    envelope = {
        "protocol_version": "mailbus-a2a/1",
        "task_id": body.get("task_id") or "dry-run",
        "intent": intent,
        "initiator": "human",
        "mode": "auto",
        "tier": body.get("tier") or "M",
        "task_type": body.get("task_type") or "custom",
        "constraints": body.get("constraints") or {},
    }
    prefer = body.get("provider") or ""
    try:
        out = dry_run(envelope, data_dir=handler.data_dir, prefer=prefer)
        handler._send_json({"status": "ok", "result": out})
    except PlanError as exc:
        handler._send_json({"status": "error", "error": exc.code, "message": str(exc)}, 400)


def handle_internal_llm_rebuild_rag(handler):
    cfg = load_llm_config(handler.data_dir)
    if not cfg.get("enabled"):
        handler._send_json({"status": "error", "error": "internal_llm disabled"}, 400)
        return
    n = rebuild_index(handler.data_dir, cfg)
    handler._send_json({"status": "ok", "chunks_indexed": n})
