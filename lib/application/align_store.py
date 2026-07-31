"""Align store query/command (CQRS-lite write companion lives with discover)."""
from __future__ import annotations

from typing import Any

from lib.application.discover_agents import align_store

__all__ = ["align_store_from_registry"]


def align_store_from_registry(data_dir: str, *, expect_min: int = 13) -> dict[str, Any]:
    return align_store(data_dir, expect_min=expect_min)
