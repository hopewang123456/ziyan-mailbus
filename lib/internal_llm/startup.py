"""Internal LLM 启动时 RAG 索引维护。"""

from __future__ import annotations

from .probe import load_llm_config


def maybe_rebuild_rag_on_start(data_dir: str) -> dict | None:
    """rebuild_on_start=true 且 chunk 数为 0 时重建索引。"""
    cfg = load_llm_config(data_dir)
    if not cfg.get("enabled"):
        return None
    rag = cfg.get("rag") or {}
    if not rag.get("enabled", True):
        return None
    idx = rag.get("index") or {}
    if not idx.get("rebuild_on_start"):
        return None
    try:
        from .rag.index import index_info, rebuild_index
    except ImportError:
        return {"rebuilt": False, "skipped": "rag.index unavailable"}
    info = index_info(data_dir, cfg)
    if info.get("chunks", 0) > 0:
        return {"rebuilt": False, "chunks": info["chunks"]}
    n = rebuild_index(data_dir, cfg)
    return {"rebuilt": True, "chunks": n}
