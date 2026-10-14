"""GET/POST /api/internal-llm/* — status / health / dry-run / rebuild-rag."""

from __future__ import annotations

from lib.application.internal_llm.planner import dry_run
# 跨层解耦：api→adapter 通过 composition 拿服务（2026-09 治理）
from lib.composition import load_llm_config_internal, probe_all_internal_llm
from lib.api.internal_llm_status import llm_status


def handle_internal_llm_status(handler):
    handler._send_json(llm_status(handler.data_dir))


def handle_internal_llm_health(handler):
    # Health uses the same provider/rag probe payload as status.
    handler._send_json(probe_all_internal_llm(handler.data_dir))


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
    cfg = load_llm_config_internal(handler.data_dir)
    try:
        # 跨层解耦：api→adapter 通过 composition 拿服务
        from lib.composition import rebuild_internal_llm_index

        n = rebuild_internal_llm_index(handler.data_dir, cfg)
    except Exception as exc:
        handler._send_json(
            {"status": "error", "error": "rebuild_failed", "message": str(exc)},
            500,
        )
        return
    handler._send_json({"status": "ok", "chunks": n})
