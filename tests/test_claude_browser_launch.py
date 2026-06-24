"""Claude ttyd 浏览器启动单元测试。"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.claude_browser_launch import (
    merge_browser_cfg,
    resolve_browser_port,
    resolve_browser_url,
    agent_has_claude_browser,
)
from lib.claude_launch import build_interactive_shell_inner


class TestClaudeBrowserLaunch(unittest.TestCase):
    def setUp(self):
        self.data_dir = os.path.join(os.path.dirname(__file__), "..", "store")

    def test_merge_browser_kind(self):
        cfg = merge_browser_cfg("lingyun", self.data_dir)
        self.assertEqual(cfg.get("kind"), "claude_ttyd")

    def test_resolve_port_lingyan(self):
        port = resolve_browser_port("lingyan", self.data_dir)
        self.assertEqual(port, 9261)

    def test_resolve_port_lingyun(self):
        port = resolve_browser_port("lingyun", self.data_dir)
        self.assertEqual(port, 9260)

    def test_agents_use_different_ports(self):
        self.assertNotEqual(
            resolve_browser_port("lingyun", self.data_dir),
            resolve_browser_port("lingyan", self.data_dir),
        )

    def test_resolve_url(self):
        url = resolve_browser_url("lingyun", self.data_dir)
        self.assertIn("9260", url)

    def test_agent_has_claude_browser(self):
        from lib.utils import json_read

        cfg = json_read(os.path.join(self.data_dir, "config.json"), {})
        agent = cfg["agents"]["lingyun"]
        types = cfg.get("agent_types") or {}
        self.assertTrue(agent_has_claude_browser(agent, types))

    def test_ensure_claude_agent_settings_inherits_base_url(self):
        import tempfile
        import shutil
        from lib.claude_launch import ensure_claude_agent_settings

        with tempfile.TemporaryDirectory() as td:
            store = os.path.join(td, "store")
            os.makedirs(store)
            base_claude = os.path.join(td, "base-claude")
            os.makedirs(base_claude)
            with open(os.path.join(base_claude, "settings.json"), "w", encoding="utf-8") as f:
                f.write('{"env":{"ANTHROPIC_BASE_URL":"https://api.minimaxi.com/anthropic"}}')
            cfg = {
                "agents": {
                    "lingyun": {"type": "claude_code", "push": {"cwd": "E:/ai_tools"}},
                    "lingyan": {"type": "claude_code", "push": {"cwd": "E:/ai_tools"}},
                },
                "mailbus_claude": {
                    "platform": "windows",
                    "windows": {"claude_home": base_claude.replace("\\", "/")},
                },
            }
            with open(os.path.join(store, "config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            info = ensure_claude_agent_settings("lingyun", store)
            settings = __import__("json").load(open(info["settings"], encoding="utf-8"))
            self.assertEqual(
                settings["env"]["ANTHROPIC_BASE_URL"],
                "https://api.minimaxi.com/anthropic",
            )
            yan = ensure_claude_agent_settings("lingyan", store)
            self.assertNotEqual(info["settings"], yan["settings"])

    def test_build_interactive_shell_inner(self):
        inner_yun = build_interactive_shell_inner("lingyun", self.data_dir)
        inner_yan = build_interactive_shell_inner("lingyan", self.data_dir)
        self.assertIn("lingyun", inner_yun)
        self.assertIn("lingyan", inner_yan)
        self.assertNotEqual(inner_yun, inner_yan)
        self.assertIn("acceptEdits", inner_yun)
        self.assertIn("dontAsk", inner_yan)
        self.assertIn("--name '", inner_yun)
        self.assertIn("--name '", inner_yan)
        self.assertIn("claude.ps1", inner_yun.lower())

    @patch("lib.claude_browser_launch._http_ready", return_value=True)
    @patch("lib.claude_browser_launch._launch_url")
    def test_launch_claude_browser_ready(self, mock_open, _mock_ready):
        from lib.claude_browser_launch import launch_claude_browser

        info = launch_claude_browser("lingyun", self.data_dir)
        self.assertEqual(info["agent"], "lingyun")
        self.assertIn("9260", info["url"])
        mock_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
