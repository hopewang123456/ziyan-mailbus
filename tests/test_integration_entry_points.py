"""Integration entry-point discovery (config / env / pkg)."""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.adapters.integrations.entry_point_discovery import (
    collect_plugin_specs,
    discover_and_register_integrations,
    ensure_integration_plugins_loaded,
    load_plugin_spec,
    reset_discovery_state_for_tests,
)
from lib.adapters.integrations.plugin_registry import get_integration, list_integrations


PLUGIN_SRC = textwrap.dedent(
    '''
    from lib.adapters.integrations.plugin_registry import register_integration

    def register():
        register_integration(
            "_ep_demo_int",
            lambda: "demo-int",
            kind="test",
            description="entry-point demo",
        )
    '''
)


class TestIntegrationEntryPointDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        reset_discovery_state_for_tests()

    def tearDown(self) -> None:
        reset_discovery_state_for_tests()

    def _install_temp_plugin(self) -> str:
        td = tempfile.mkdtemp(prefix="mailbus-int-ep-")
        pkg = Path(td) / "ep_demo_integration"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(PLUGIN_SRC, encoding="utf-8")
        sys.path.insert(0, td)

        def _cleanup() -> None:
            if td in sys.path:
                sys.path.remove(td)

        self.addCleanup(_cleanup)
        return "ep_demo_integration:register"

    def test_collect_from_config_and_env(self) -> None:
        cfg = {"integrations": {"plugins": ["pkg.a", "pkg.b:register"]}}
        with patch.dict(os.environ, {"MAILBUS_INTEGRATION_PLUGINS": "pkg.c,pkg.a"}, clear=False):
            specs = collect_plugin_specs(config=cfg)
        self.assertEqual(specs[:3], ["pkg.a", "pkg.b:register", "pkg.c"])

    def test_load_registers_integration(self) -> None:
        spec = self._install_temp_plugin()
        row = load_plugin_spec(spec)
        self.assertTrue(row["ok"])
        self.assertIsNotNone(get_integration("_ep_demo_int"))
        names = {i["name"] for i in list_integrations()}
        self.assertIn("_ep_demo_int", names)
        row2 = load_plugin_spec(spec)
        self.assertTrue(row2.get("skipped"))

    def test_discover_via_config(self) -> None:
        spec = self._install_temp_plugin()
        results = discover_and_register_integrations(
            config={"integrations": {"plugins": [spec]}},
        )
        self.assertTrue(any(r.get("ok") and r.get("spec") == spec for r in results))

    def test_ensure_repeat_safe(self) -> None:
        spec = self._install_temp_plugin()
        with patch.dict(os.environ, {"MAILBUS_INTEGRATION_PLUGINS": spec}, clear=False):
            a = ensure_integration_plugins_loaded()
            b = ensure_integration_plugins_loaded()
        self.assertTrue(any(r.get("ok") for r in a))
        self.assertTrue(all(r.get("skipped") or r.get("ok") for r in b))


if __name__ == "__main__":
    unittest.main()
