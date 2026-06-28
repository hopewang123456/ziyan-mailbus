"""claude_launch 平台桥接单元测试。"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.claude_launch import (
    build_push_command,
    build_interactive_command,
    host_cli_active,
    load_mailbus_claude,
    resolve_claude_home,
    resolve_claude_platform,
    resolve_claude_workspace,
    resolve_project_dir,
    resolve_windows_claude_bin,
    try_build_push_direct,
    _build_interactive_ps_inner,
    _interactive_claude_flags,
)


AGENT_CFG = {
    "type": "claude_code",
    "models": ["minimax-m2"],
    "push": {"cwd": r"E:\ai_tools"},
}

TYPES = {
    "models": {
        "minimax-m2": {"claude_code": "--model MiniMax-M2.7"},
    },
}


class TestClaudeLaunch(unittest.TestCase):
    def test_load_mailbus_claude_from_store(self):
        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        cfg = load_mailbus_claude(data_dir)
        self.assertIn("windows", cfg)
        self.assertIn("linux", cfg)

    def test_resolve_platform_auto(self):
        cfg = {"platform": "auto"}
        plat = resolve_claude_platform(cfg)
        self.assertIn(plat, ("windows", "linux"))

    def test_resolve_project_dir_prefers_push_cwd(self):
        plat = {"default_project_dir": "/tmp"}
        self.assertEqual(
            resolve_project_dir(AGENT_CFG, plat, "lingyun"),
            "E:/ai_tools",
        )

    def test_resolve_claude_home_per_agent(self):
        plat = {"claude_home": r"C:\Users\hopew\.claude"}
        yun = resolve_claude_home(plat, "lingyun")
        yan = resolve_claude_home(plat, "lingyan")
        self.assertIn("lingyun", yun)
        self.assertIn("lingyan", yan)
        self.assertNotEqual(yun, yan)

    def test_resolve_claude_workspace_isolated(self):
        plat = {}
        ws_yun = resolve_claude_workspace(AGENT_CFG, plat, "lingyun")
        ws_yan = resolve_claude_workspace(AGENT_CFG, plat, "lingyan")
        self.assertIn("lingyun", ws_yun)
        self.assertIn("lingyan", ws_yan)
        self.assertNotEqual(ws_yun, ws_yan)

    @patch("lib.claude_launch.resolve_claude_platform", return_value="windows")
    @patch("lib.claude_launch._runtime_os", return_value="linux")
    def test_push_windows_from_wsl_uses_powershell(self, *_mocks):
        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        cmd = build_push_command(
            "lingyun", AGENT_CFG, TYPES, "minimax-m2", data_dir=data_dir,
        )
        self.assertIn("powershell", cmd.lower())
        self.assertIn("claude", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("'MSG'", cmd)
        self.assertIn("acceptEdits", cmd)
        self.assertIn("MiniMax-M2.7", cmd)
        self.assertNotIn("-it", cmd)

    @patch("lib.claude_launch._platform_enabled", return_value=True)
    @patch("lib.claude_launch.resolve_claude_platform", return_value="linux")
    @patch("lib.claude_launch._runtime_os", return_value="linux")
    def test_push_linux_native_bash(self, *_mocks):
        cfg = dict(AGENT_CFG)
        cfg["push"] = {"cwd": "/mnt/e/ai_tools"}
        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        cmd = build_push_command("lingyun", cfg, TYPES, data_dir=data_dir)
        self.assertIn("bash -lc", cmd)
        self.assertIn("claude", cmd)
        self.assertIn("-p", cmd)

    @patch("lib.claude_launch.resolve_claude_platform", return_value="windows")
    @patch("lib.claude_launch._runtime_os", return_value="windows")
    def test_interactive_windows_no_exit(self, *_mocks):
        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        cmd = build_interactive_command("lingyun", AGENT_CFG, TYPES, data_dir=data_dir)
        self.assertIn("NoExit", cmd)
        self.assertIn("claude", cmd.lower())

    @patch("lib.claude_launch.resolve_windows_claude_bin", return_value="E:/nodejs/node_global/claude.ps1")
    def test_interactive_ps_inner_uses_full_claude_path(self, *_mocks):
        cfg = dict(AGENT_CFG)
        cfg["name"] = "灵云"
        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        inner = _build_interactive_ps_inner("lingyun", cfg, TYPES, data_dir)
        self.assertIn("E:/nodejs/node_global/claude.ps1", inner)
        self.assertIn("CLAUDE_CONFIG_DIR", inner)
        self.assertIn("灵云", inner)
        self.assertIn("--name '", inner)

    def test_interactive_flags_use_single_quotes(self):
        flags = _interactive_claude_flags("lingyun", AGENT_CFG, TYPES)
        self.assertIn("--name '", flags)
        self.assertNotIn('--name "灵云"', flags)

    @patch("lib.claude_launch._spawn_powershell_interactive")
    @patch("lib.claude_launch._sync_claude_agent_context")
    def test_launch_claude_cli_windows(self, _sync, _spawn):
        from lib.claude_launch import launch_claude_cli

        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        info = launch_claude_cli("lingyun", data_dir)
        self.assertEqual(info["agent"], "lingyun")
        self.assertEqual(info["kind"], "claude_cli")
        _spawn.assert_called_once()
        _sync.assert_called_once()

    def test_lingyan_push_uses_dontask_tools(self):
        cfg = {
            "type": "claude_code",
            "models": ["minimax-m2"],
            "claude": {
                "permission_mode": "dontAsk",
                "push_flags": '--allowedTools "Bash,Read,Glob,Grep"',
            },
            "push": {"cwd": r"E:\ai_tools"},
        }
        from lib.claude_launch import _claude_push_flags

        flags = _claude_push_flags("lingyan", cfg, TYPES, "minimax-m2")
        self.assertIn("dontAsk", flags)
        self.assertIn("Bash,Read,Glob,Grep", flags)
        self.assertNotIn("acceptEdits", flags)

    def test_lingyun_push_uses_accept_edits(self):
        cfg = {
            "type": "claude_code",
            "claude": {"permission_mode": "acceptEdits"},
        }
        from lib.claude_launch import _claude_push_flags

        flags = _claude_push_flags("lingyun", cfg, TYPES, None)
        self.assertIn("acceptEdits", flags)

    def test_host_cli_active_detects_print_mode(self):
        ps = "hopew 123 claude -p 'mailbus task' --permission-mode acceptEdits\n"
        self.assertTrue(host_cli_active(ps))
        self.assertFalse(host_cli_active("hopew 1 tail -f /dev/null\n"))

    @patch("lib.claude_launch.resolve_windows_claude_bin", return_value="E:/nodejs/node_global/claude.cmd")
    @patch("lib.claude_launch.resolve_claude_platform", return_value="windows")
    @patch("lib.claude_launch._runtime_os", return_value="windows")
    def test_try_build_push_direct_on_windows_native(self, *_mocks):
        if sys.platform != "win32":
            self.skipTest("Windows-only direct push")
        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        spec = try_build_push_direct(
            "lingyun",
            AGENT_CFG,
            TYPES,
            data_dir=data_dir,
            prompt="line1\nit's quoted\npath=E:/ai_tools",
        )
        self.assertIsNotNone(spec)
        self.assertIn("-p", spec["argv"])
        idx = spec["argv"].index("-p")
        self.assertEqual(spec["argv"][idx + 1], "line1\nit's quoted\npath=E:/ai_tools")
        self.assertIn("CLAUDE_CONFIG_DIR", spec["env"])
        self.assertTrue(spec["cwd"])

    @patch("lib.claude_launch.resolve_claude_bin", return_value="claude")
    @patch("lib.claude_launch.resolve_claude_plat_cfg", return_value=("linux", {"claude_bin": "claude"}))
    @patch("lib.claude_launch.resolve_claude_platform", return_value="linux")
    @patch("lib.claude_launch._runtime_os", return_value="linux")
    def test_try_build_push_direct_on_linux(self, *_mocks):
        data_dir = os.path.join(os.path.dirname(__file__), "..", "store")
        spec = try_build_push_direct(
            "lingyun",
            AGENT_CFG,
            TYPES,
            data_dir=data_dir,
            prompt="hello",
        )
        self.assertIsNotNone(spec)
        self.assertIn("-p", spec["argv"])
        self.assertEqual(spec["argv"][spec["argv"].index("-p") + 1], "hello")


if __name__ == "__main__":
    unittest.main()
