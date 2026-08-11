"""Load-time integration plugin discovery (no hot-reload).

Sources: config ``integrations.plugins`` / ``plugins.integrations``;
env ``MAILBUS_INTEGRATION_PLUGINS``; pkg group ``mailbus.integrations``.

Callables should use ``register_integration`` (see plugin_registry).
"""
from __future__ import annotations

from typing import Any

from lib.adapters.integrations.plugin_discovery import PluginDiscovery

ENTRY_POINT_GROUP = "mailbus.integrations"

_DISCOVERY = PluginDiscovery(
    name="integrations",
    entry_point_group=ENTRY_POINT_GROUP,
    config_paths=(("integrations", "plugins"), ("plugins", "integrations")),
    env_var="MAILBUS_INTEGRATION_PLUGINS",
    strict_env="MAILBUS_INTEGRATION_PLUGINS_STRICT",
)


def reset_discovery_state_for_tests() -> None:
    _DISCOVERY.reset_for_tests()


def discovery_results() -> list[dict[str, Any]]:
    return _DISCOVERY.results()


def collect_plugin_specs(*, config: dict | None = None) -> list[str]:
    return _DISCOVERY.collect(config)


def load_plugin_spec(spec: str) -> dict[str, Any]:
    return _DISCOVERY.load_spec(spec)


def discover_and_register_integrations(
    *,
    data_dir: str = "",
    config: dict | None = None,
) -> list[dict[str, Any]]:
    return _DISCOVERY.discover(data_dir=data_dir, config=config)


def ensure_integration_plugins_loaded(*, data_dir: str = "", config: dict | None = None) -> list[dict[str, Any]]:
    return discover_and_register_integrations(data_dir=data_dir, config=config)
