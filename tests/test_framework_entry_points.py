"""W7: framework entry-point discovery (config / env / pkg)."""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.adapters.frameworks.entry_point_discovery import (
    collect_plugin_specs,
    discover_and_register_frameworks,
    ensure_framework_plugins_loaded,
    load_plugin_spec,
    reset_discovery_state_for_tests,
)
from lib.adapters.frameworks.registry import get_adapter, unregister_framework


PLUGIN_SRC = textwrap.dedent(
    '''
    from lib.adapters.frameworks.registry import BaseAdapter, register_framework

    class _EpDemoAdapter(BaseAdapter):
        def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None, **kw):
            return "echo ep-demo"

    def register():
        register_framework("_ep_demo_fw", _EpDemoAdapter(), replace=True)
    '''
)


class TestFrameworkEntryPointDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        reset_discovery_state_for_tests()
        unregister_framework("_ep_demo_fw")

    def tearDown(self) -> None:
        unregister_framework("_ep_demo_fw")
        reset_discovery_state_for_tests()

    def _install_temp_plugin(self) -> str:
        td = tempfile.mkdtemp(prefix="mailbus-ep-")
        pkg = Path(td) / "ep_demo_plugin"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(PLUGIN_SRC, encoding="utf-8")
        sys.path.insert(0, td)

        def _cleanup() -> None:
            if td in sys.path:
                sys.path.remove(td)
            unregister_framework("_ep_demo_fw")

        self.addCleanup(_cleanup)
        return "ep_demo_plugin:register"

    def test_collect_from_config_and_env(self) -> None:
        cfg = {"frameworks": {"plugins": ["pkg.a", "pkg.b:register"]}}
        with patch.dict(os.environ, {"MAILBUS_FRAMEWORK_PLUGINS": "pkg.c,pkg.a"}, clear=False):
            specs = collect_plugin_specs(config=cfg)
        self.assertEqual(specs[:3], ["pkg.a", "pkg.b:register", "pkg.c"])

    def test_load_module_callable_registers(self) -> None:
        spec = self._install_temp_plugin()
        row = load_plugin_spec(spec)
        self.assertTrue(row["ok"])
        self.assertIsNotNone(get_adapter("_ep_demo_fw"))
        # idempotent
        row2 = load_plugin_spec(spec)
        self.assertTrue(row2.get("skipped"))

    def test_discover_via_config(self) -> None:
        spec = self._install_temp_plugin()
        results = discover_and_register_frameworks(config={"frameworks": {"plugins": [spec]}})
        self.assertTrue(any(r.get("ok") and r.get("spec") == spec for r in results))
        self.assertIsNotNone(get_adapter("_ep_demo_fw"))

    def test_ensure_is_safe_repeat(self) -> None:
        spec = self._install_temp_plugin()
        with patch.dict(os.environ, {"MAILBUS_FRAMEWORK_PLUGINS": spec}, clear=False):
            a = ensure_framework_plugins_loaded()
            b = ensure_framework_plugins_loaded()
        self.assertTrue(any(r.get("ok") for r in a))
        self.assertTrue(all(r.get("skipped") or r.get("ok") for r in b))


if __name__ == "__main__":
    unittest.main()
