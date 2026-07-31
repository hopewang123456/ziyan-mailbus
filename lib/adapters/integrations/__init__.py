"""Optional integrations (Wave4 · Q10B) — outside mailbus core path."""
from __future__ import annotations

from lib.adapters.integrations.plugin_registry import (
    get_integration,
    invoke,
    list_integrations,
    register_integration,
)

__all__ = [
    "get_integration",
    "invoke",
    "list_integrations",
    "register_integration",
]
