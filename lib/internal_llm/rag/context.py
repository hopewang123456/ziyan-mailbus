"""Planner RAG 上下文块 — plan / replan / llm_adaptive 共用。"""

from __future__ import annotations

from typing import List, Tuple

from .index import retrieve


def format_rag_block(citations: List[dict], *, style: str = "plan") -> str:
    if not citations:
        return "(no rag hits)"
    if style == "route":
        return "\n".join(f"[{c['source_id']}] {c['excerpt'][:200]}" for c in citations)
    return "\n\n".join(
        f"[{c['source_id']}] {c.get('title', '')}: {c['excerpt'][:240]}"
        for c in citations
    )


def fetch_rag_context(
    data_dir: str,
    cfg: dict,
    query: str,
    *,
    top_k: int = 8,
    style: str = "plan",
) -> Tuple[List[dict], str]:
    rag = cfg.get("rag") or {}
    if not rag.get("enabled", True):
        return [], "(rag disabled)"
    citations = retrieve(data_dir, cfg, query, top_k=top_k)
    return citations, format_rag_block(citations, style=style)
