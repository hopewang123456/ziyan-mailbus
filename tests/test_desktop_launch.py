"""Desktop 启动配置检测。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.frameworks.desktop_launch import (
    agent_has_desktop,
    merge_launch_desktop,
    resolve_platform,
)


class TestDesktopLaunch(unittest.TestCase):
    def _agents(self):
        from lib.infra.utils import json_read

        cfg = json_read(os.path.join(os.path.dirname(__file__), "..", "store", "config.json"), {})
        return cfg.get("agents") or {}, cfg.get("agent_types") or {}

    def test_desktop_disabled_for_non_desktop_frameworks(self):
        agents, types = self._agents()
        codex = next((a for a, c in agents.items() if (c.get("type") or "").startswith("codex")), None)
        opencode = next((a for a, c in agents.items() if c.get("type") == "opencode"), None)
        if codex is None and opencode is None:
            self.skipTest("no codex/opencode agent in store config")
        for name in (codex, opencode):
            if name:
                self.assertFalse(agent_has_desktop(agents[name], types))

    def test_claude_desktop_disabled(self):
        agents, types = self._agents()
        claude = [a for a, c in agents.items() if c.get("type") == "claude_code"]
        if not claude:
            self.skipTest("no claude_code agent in store config")
        for name in claude[:2]:
            self.assertFalse(agent_has_desktop(agents[name], types))

    def test_claude_has_browser_config(self):
        from lib.adapters.frameworks.claude_browser_launch import agent_has_claude_browser

        agents, types = self._agents()
        claude = [a for a, c in agents.items() if c.get("type") == "claude_code"]
        if not claude:
            self.skipTest("no claude_code agent in store config")
        name = claude[0]
        self.assertTrue(agent_has_claude_browser(agents[name], types))

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
