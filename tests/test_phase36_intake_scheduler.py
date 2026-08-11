"""Phase 3.6 — intake bridge + scheduler jobs SoT."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.config.init_store import load_config_fragments
from lib.application.workflow.intake.spawn_rules import DEFAULT_BRIDGE_CONFIG, load_bridge_config


class TestIntakeBridgeConfig(unittest.TestCase):
    def test_static_bridge_json_exists(self):
        from lib.infra.constants import MAILBUS_ROOT
        path = MAILBUS_ROOT / "config" / "intake" / "bridge.json"
        self.assertTrue(path.is_file(), str(path))

    def test_init_store_merges_bridge(self):
        frags = load_config_fragments()
        bridge = frags.get("mailbus_intake_bridge") or {}
        self.assertIn("enabled", bridge)
        self.assertIn("auto_spawn_analyze", bridge)

    def test_load_bridge_config_from_store(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = os.path.join(td, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"mailbus_intake_bridge": {"auto_spawn_content": True}}, f)
            bridge = load_bridge_config(td)
            self.assertTrue(bridge.get("auto_spawn_content"))
            self.assertEqual(bridge.get("auto_spawn_analyze"), DEFAULT_BRIDGE_CONFIG["auto_spawn_analyze"])


class TestSchedulerJobsSoT(unittest.TestCase):
    def test_jobs_json_has_core_jobs(self):
        from lib.infra.constants import MAILBUS_ROOT
        path = MAILBUS_ROOT / "config" / "scheduler" / "jobs.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = {j["id"] for j in data.get("jobs") or []}
        for jid in ("scan", "memory_bridge", "intake-bridge", "lingxun_patrol"):
            self.assertIn(jid, ids)


if __name__ == "__main__":
    unittest.main()
