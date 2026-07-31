"""Optional integrations (Wave4 · Q10B) — outside mailbus core path."""
from __future__ import annotations

from lib.adapters.integrations.plugin_registry import (
    get_integration,
    invoke,
    list_integrations,
    register_integration,
)

try:
    from lib.adapters.integrations.entry_point_discovery import (
        discover_and_register_integrations,
        ensure_integration_plugins_loaded,
    )
except Exception:  # pragma: no cover
    discover_and_register_integrations = None  # type: ignore[assignment]
    ensure_integration_plugins_loaded = None  # type: ignore[assignment]

__all__ = [
    "get_integration",
    "invoke",
    "list_integrations",
    "register_integration",
    "discover_and_register_integrations",
    "ensure_integration_plugins_loaded",
]
