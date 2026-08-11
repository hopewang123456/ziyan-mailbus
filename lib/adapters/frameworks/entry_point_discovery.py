"""Load-time framework plugin discovery (W7 · no hot-reload).

Sources: config ``frameworks.plugins`` / ``plugins.frameworks``;
env ``MAILBUS_FRAMEWORK_PLUGINS``; pkg group ``mailbus.frameworks``.
"""
from __future__ import annotations

from typing import Any

from lib.adapters.integrations.plugin_discovery import PluginDiscovery

ENTRY_POINT_GROUP = "mailbus.frameworks"

_DISCOVERY = PluginDiscovery(
    name="frameworks",
    entry_point_group=ENTRY_POINT_GROUP,
    config_paths=(("frameworks", "plugins"), ("plugins", "frameworks")),
    env_var="MAILBUS_FRAMEWORK_PLUGINS",
    strict_env="MAILBUS_FRAMEWORK_PLUGINS_STRICT",
)


def reset_discovery_state_for_tests() -> None:
    _DISCOVERY.reset_for_tests()


def discovery_results() -> list[dict[str, Any]]:
    return _DISCOVERY.results()


def collect_plugin_specs(*, config: dict | None = None) -> list[str]:
    return _DISCOVERY.collect(config)


def load_plugin_spec(spec: str) -> dict[str, Any]:
    return _DISCOVERY.load_spec(spec)


def discover_and_register_frameworks(
    *,
    data_dir: str = "",
    config: dict | None = None,
) -> list[dict[str, Any]]:
    return _DISCOVERY.discover(data_dir=data_dir, config=config)


def ensure_framework_plugins_loaded(*, data_dir: str = "", config: dict | None = None) -> list[dict[str, Any]]:
    return discover_and_register_frameworks(data_dir=data_dir, config=config)
