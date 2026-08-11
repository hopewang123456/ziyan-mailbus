"""Tests for launch_ports settings API."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from lib.adapters.config.config_admin import get_section, patch_section
from lib.infra.utils import json_write


class LaunchPortsSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, "store")
        os.makedirs(self.data_dir)
        cfg = {
            "agents": {
                "lingxi": {
                    "name": "灵犀",
                    "type": "hermes_profile",
                    "docker": {"port": 9122},
                    "launch": {"template": "hermes_dashboard", "has_browser": True},
                }
            },
            "agent_types": {
                "launch_templates": {
                    "hermes_dashboard": {
                        "browser": {
                            "kind": "hermes_dashboard",
                            "url": "http://localhost:{port}/chat",
                        }
                    }
                }
            },
        }
        json_write(os.path.join(self.data_dir, "config.json"), cfg)

    def test_get_launch_ports_section(self) -> None:
        sec = get_section(self.data_dir, "launch_ports")
        self.assertEqual(sec["section"], "launch_ports")
        self.assertEqual(len(sec["agents"]), 1)
        self.assertEqual(sec["agents"][0]["port"], 9122)

    def test_patch_launch_ports_custom(self) -> None:
        patch_section(
            self.data_dir,
            "launch_ports",
            {"updates": [{"agent_id": "lingxi", "port": 9999}]},
        )
        cfg = json.load(open(os.path.join(self.data_dir, "config.json"), encoding="utf-8"))
        self.assertEqual(cfg["agents"]["lingxi"]["launch"]["browser"]["dashboard_port"], 9999)

    def test_patch_launch_ports_reset(self) -> None:
        patch_section(
            self.data_dir,
            "launch_ports",
            {"updates": [{"agent_id": "lingxi", "port": 9999}]},
        )
        patch_section(
            self.data_dir,
            "launch_ports",
            {"updates": [{"agent_id": "lingxi", "reset": True}]},
        )
        cfg = json.load(open(os.path.join(self.data_dir, "config.json"), encoding="utf-8"))
        browser = cfg["agents"]["lingxi"]["launch"]["browser"]
        self.assertNotIn("dashboard_port", browser)


if __name__ == "__main__":
    unittest.main()
