"""Claude ttyd 浏览器启动单元测试。"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.frameworks.claude_browser_launch import (
    merge_browser_cfg,
    resolve_browser_port,
    resolve_browser_url,
    agent_has_claude_browser,
)
from lib.adapters.frameworks.claude_launch import build_interactive_shell_inner


class TestClaudeBrowserLaunch(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self._td.name, "store")
        os.makedirs(self.data_dir)
        os.makedirs(os.path.join(self._td.name, "base-claude"))
        cfg = {
            "agents": {
                "agent-h": {
                    "type": "claude_code",
                    "push": {"cwd": "<PROJECT_ROOT>"},
                    "launch": {"template": "claude_host", "browser": {"web_port": "9260"}},
                },
                "agent-f": {
                    "type": "claude_code",
                    "push": {"cwd": "<PROJECT_ROOT>"},
                    "launch": {"template": "claude_host", "browser": {"web_port": "9261"}},
                },
            },
            "agent_types": {
                "launch_templates": {
                    "claude_host": {
                        "browser": {"kind": "claude_ttyd", "url": "http://127.0.0.1:{port}/"},
                    }
                }
            },
            "mailbus_claude": {
                "platform": "windows",
                "windows": {
                    "claude_home": os.path.join(self._td.name, "base-claude").replace("\\", "/"),
                },
            },
        }
        with open(os.path.join(self.data_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def tearDown(self):
        self._td.cleanup()

    def test_merge_browser_kind(self):
        cfg = merge_browser_cfg("agent-h", self.data_dir)
        self.assertEqual(cfg.get("kind"), "claude_ttyd")

    def test_resolve_port_agent_f(self):
        port = resolve_browser_port("agent-f", self.data_dir)
        self.assertEqual(port, 9261)

    def test_resolve_port_agent_h(self):
        port = resolve_browser_port("agent-h", self.data_dir)
        self.assertEqual(port, 9260)

    def test_agents_use_different_ports(self):
        self.assertNotEqual(
            resolve_browser_port("agent-h", self.data_dir),
            resolve_browser_port("agent-f", self.data_dir),
        )

    def test_resolve_url(self):
        url = resolve_browser_url("agent-h", self.data_dir)
        self.assertIn("9260", url)

    def test_agent_has_claude_browser(self):
        from lib.infra.utils import json_read

        cfg = json_read(os.path.join(self.data_dir, "config.json"), {})
        agent = cfg["agents"]["agent-h"]
        types = cfg.get("agent_types") or {}
        self.assertTrue(agent_has_claude_browser(agent, types))

    def test_ensure_claude_agent_settings_inherits_base_url(self):
        import shutil
        from lib.adapters.frameworks.claude_launch import ensure_claude_agent_settings

        base_claude = os.path.join(self._td.name, "base-claude")
        with open(os.path.join(base_claude, "settings.json"), "w", encoding="utf-8") as f:
            f.write('{"env":{"ANTHROPIC_BASE_URL":"https://api.minimaxi.com/anthropic"}}')
        cfg = {
            "agents": {
                "agent-h": {"type": "claude_code", "push": {"cwd": "<PROJECT_ROOT>"}},
                "agent-f": {"type": "claude_code", "push": {"cwd": "<PROJECT_ROOT>"}},
            },
            "mailbus_claude": {
                "platform": "windows",
                "windows": {"claude_home": base_claude.replace("\\", "/")},
            },
        }
        with open(os.path.join(self.data_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        info = ensure_claude_agent_settings("agent-h", self.data_dir)
        settings = __import__("json").load(open(info["settings"], encoding="utf-8"))
        self.assertEqual(
            settings["env"]["ANTHROPIC_BASE_URL"],
            "https://api.minimaxi.com/anthropic",
        )
        yan = ensure_claude_agent_settings("agent-f", self.data_dir)
        self.assertNotEqual(info["settings"], yan["settings"])

    def test_build_interactive_shell_inner(self):
        import tempfile
        import shutil

        with tempfile.TemporaryDirectory() as td:
            store = os.path.join(td, "store")
            os.makedirs(store)
            base_cfg = {
                "agents": {
                    "agent-a": {
                        "type": "claude_code",
                        "name": "Agent A",
                        "claude": {"interactive_permission_mode": "dontAsk"},
                    },
                    "agent-b": {"type": "claude_code", "name": "Agent B"},
                },
                "mailbus_claude": {
                    "platform": "linux",
                    "linux": {"claude_home": "/tmp/claude-home", "default_project_dir": "/tmp/workspace"},
                },
            }
            with open(os.path.join(store, "config.json"), "w", encoding="utf-8") as f:
                json.dump(base_cfg, f)
            inner_a = build_interactive_shell_inner("agent-a", store)
            inner_b = build_interactive_shell_inner("agent-b", store)
            self.assertIn("agent-a", inner_a)
            self.assertIn("agent-b", inner_b)
            self.assertIn("dontAsk", inner_a)
            self.assertIn("acceptEdits", inner_b)
            self.assertIn("--name '", inner_a)
            self.assertIn("--name '", inner_b)
            # linux/wsl 路径直接 exec claude；windows bridge 才走 claude.ps1
            self.assertTrue(
                "claude" in inner_a.lower(),
                msg=f"expected claude binary in: {inner_a}",
            )

    @patch("lib.adapters.frameworks.claude_browser_launch._http_ready", return_value=True)
    @patch("lib.adapters.frameworks.claude_browser_launch._launch_url")
    def test_launch_claude_browser_ready(self, mock_open, _mock_ready):
        from lib.adapters.frameworks.claude_browser_launch import launch_claude_browser

        info = launch_claude_browser("agent-h", self.data_dir)
        self.assertEqual(info["agent"], "agent-h")
        self.assertIn("9260", info["url"])
        mock_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
