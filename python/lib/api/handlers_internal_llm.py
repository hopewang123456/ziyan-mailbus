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


def handle_assistant_ask(handler):
    """POST /api/assistant/ask — AI 助手问答（P2 D10/D11，B6 语义层纪律）。

    上下文三源：① 指标 manifest+当前值（走语义层，LLM 不摸原始数据）
    ② RAG 手册片段（docs/ 知识库）③ 用户问题。LLM 不可达显式 503。
    """
    body = handler._read_post_body()
    question = str(body.get("question") or "").strip()
    if not question:
        handler._send_api_error("fatal", 400, detail="缺少 question")
        return

    from lib.composition import (
        complete_llm,
        llm_error_type,
        load_llm_config_internal,
        retrieve_context,
        metrics_manifest,
        metrics_query,
    )

    cfg = load_llm_config_internal(handler.data_dir)

    # ① 指标语义层注入（B6）：manifest 名称+口径+当前值
    manifest = metrics_manifest(handler.data_dir)
    points = (metrics_query(handler.data_dir) or {}).get("points") or []
    values = {p.get("metric"): p.get("value") for p in points}
    metric_lines = []
    for m in manifest.get("metrics") or []:
        mid = str(m.get("id"))
        v = values.get(mid)
        if v is None:
            continue
        name = (m.get("name") or {}).get("zh") or mid
        metric_lines.append(f"- {name}({mid}) = {v} {m.get('unit') or ''}｜口径: {m.get('description') or ''}")
    metrics_block = "\n".join(metric_lines) or "（指标暂不可用）"

    # ② RAG 手册片段
    citations = retrieve_context(handler.data_dir, cfg, question, top_k=5)
    rag_lines = [
        f"[{c.get('source_id')}/{c.get('title')}] {str(c.get('excerpt'))[:300]}"
        for c in citations
    ]
    rag_block = "\n".join(rag_lines) or "（无手册命中）"

    system = (
        "你是 mailbus 的内置 AI 助手（子言的参谋）。回答用户关于 mailbus 系统的问题：\n"
        "- 涉及指标/系统状态时，仅依据下方「当前指标」块作答，不要编造数字；\n"
        "- 涉及操作/架构时，优先引用「手册片段」，注明来源（source/title）；\n"
        "- 手册与指标都没有答案时，明确说不知道并建议查看哪个 runbook；\n"
        "- 用中文，简洁，先给结论。\n\n"
        f"【当前指标】\n{metrics_block}\n\n"
        f"【手册片段】\n{rag_block}"
    )

    try:
        answer = complete_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": question}],
            cfg,
        )
    except llm_error_type() as exc:
        handler._send_json(
            {"status": "error", "error": "llm_unavailable", "message": str(exc)}, 503
        )
        return
    handler._send_json({
        "status": "ok",
        "answer": str(answer),
        "citations": [
            {"source_id": c.get("source_id"), "title": c.get("title")}
            for c in citations
        ],
    })
