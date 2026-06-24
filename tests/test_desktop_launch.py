"""Desktop 启动配置检测。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.desktop_launch import (
    agent_has_desktop,
    merge_launch_desktop,
    resolve_platform,
)


class TestDesktopLaunch(unittest.TestCase):
    def test_lingxiao_desktop_disabled_in_config(self):
        from lib.utils import json_read

        cfg = json_read(os.path.join(os.path.dirname(__file__), "..", "store", "config.json"), {})
        agents = cfg.get("agents") or {}
        types = cfg.get("agent_types") or {}
        self.assertIn("lingxiao", agents)
        self.assertFalse(agent_has_desktop(agents["lingxiao"], types))
        self.assertFalse(agent_has_desktop(agents.get("lingjian", {}), types))
        self.assertFalse(agent_has_desktop(agents.get("dali", {}), types))

    def test_lingyun_lingyan_desktop_disabled(self):
        from lib.utils import json_read

        cfg = json_read(os.path.join(os.path.dirname(__file__), "..", "store", "config.json"), {})
        agents = cfg.get("agents") or {}
        types = cfg.get("agent_types") or {}
        for name in ("lingyun", "lingyan"):
            self.assertIn(name, agents)
            self.assertFalse(agent_has_desktop(agents[name], types))

    def test_lingyun_has_browser_config(self):
        from lib.utils import json_read
        from lib.claude_browser_launch import agent_has_claude_browser

        cfg = json_read(os.path.join(os.path.dirname(__file__), "..", "store", "config.json"), {})
        agents = cfg.get("agents") or {}
        types = cfg.get("agent_types") or {}
        self.assertTrue(agent_has_claude_browser(agents["lingyun"], types))

    def test_merge_launch_desktop_agent_override(self):
        agent_types = {"launch_templates": {"codex_docker": {"desktop": {"kind": "codex_desktop"}}}}
        agent_cfg = {"launch": {"template": "codex_docker", "desktop": {"enabled": True, "gateway_port": 9220}}}
        merged = merge_launch_desktop(agent_cfg, agent_types)
        self.assertEqual(merged.get("kind"), "codex_desktop")
        self.assertEqual(merged.get("gateway_port"), 9220)

    def test_resolve_platform_auto(self):
        plat = resolve_platform({"platform": "auto"})
        self.assertIn(plat, ("windows", "linux"))


if __name__ == "__main__":
    unittest.main()
