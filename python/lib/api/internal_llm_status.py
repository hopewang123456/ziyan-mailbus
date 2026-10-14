"""Internal LLM status snapshot for API / probes."""

from __future__ import annotations


def llm_status(data_dir: str) -> dict:
    """Return enabled/providers/rag readiness for /api/internal-llm/status."""
    # 跨层解耦：api→adapter 通过 composition 拿服务（2026-09 治理）
    from lib.composition import probe_all_internal_llm
    return probe_all_internal_llm(data_dir)
