"""GET/POST /api/internal-llm/* — status / health / dry-run / rebuild-rag."""

from __future__ import annotations

from lib.application.internal_llm.planner import dry_run
from lib.adapters.internal_llm.probe import load_llm_config, probe_all
from lib.api.internal_llm_status import llm_status


def handle_internal_llm_status(handler):
    handler._send_json(llm_status(handler.data_dir))


def handle_internal_llm_health(handler):
    # Health uses the same provider/rag probe payload as status.
    handler._send_json(probe_all(handler.data_dir))


def handle_internal_llm_dry_run(handler):
    body = handler._read_post_body() or {}
    prefer = (body.get("provider") or "").strip()
    try:
        result = dry_run(body, data_dir=handler.data_dir, prefer=prefer)
    except Exception as exc:
        code = getattr(exc, "code", "dry_run_failed")
        handler._send_json(
            {"status": "error", "error": code, "message": str(exc)},
            400,
        )
        return
    handler._send_json({"status": "ok", "result": result})


def handle_internal_llm_rebuild_rag(handler):
    cfg = load_llm_config(handler.data_dir)
    try:
        from lib.adapters.internal_llm.index import rebuild_index

        n = rebuild_index(handler.data_dir, cfg)
    except Exception as exc:
        handler._send_json(
            {"status": "error", "error": "rebuild_failed", "message": str(exc)},
            500,
        )
        return
    handler._send_json({"status": "ok", "chunks": n})
