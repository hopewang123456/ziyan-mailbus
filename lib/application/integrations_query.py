"""Integrations query for settings / clinic (Wave4–5)."""
from __future__ import annotations

from lib.adapters.integrations.plugin_registry import list_integrations
from lib.domain.types import IntegrationItemView, IntegrationsOverviewView


def integrations_overview(data_dir: str = "") -> IntegrationsOverviewView:
    """List registered optional integrations (bounded context outside core)."""
    items: list[IntegrationItemView] = list_integrations()  # type: ignore[assignment]
    return {
        "ok": True,
        "count": len(items),
        "integrations": items,
        "note": "optional adapters under lib/adapters/integrations/ — not on mailbus core path",
        "data_dir": data_dir or "",
    }
