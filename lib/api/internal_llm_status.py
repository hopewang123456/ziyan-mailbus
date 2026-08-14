"""Internal LLM status snapshot for API / probes."""

from __future__ import annotations

from lib.adapters.internal_llm.probe import probe_all


def llm_status(data_dir: str) -> dict:
    """Return enabled/providers/rag readiness for /api/internal-llm/status."""
    return probe_all(data_dir)
