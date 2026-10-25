"""agent_push 跨平台 argv 构建。"""
import os
from lib.infra.constants import PROJECT_ROOT
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.frameworks.direct_push import try_build_push_direct


class TestAgentPush(unittest.TestCase):
    @patch("lib.adapters.frameworks.direct_push._docker_bin", return_value="docker")
    def test_codex_direct_argv(self, *_m):
        spec = try_build_push_direct(
            "agent-g",
            {
                "type": "codex",
                "models": ["deepseek-flash"],
                "docker": {"service": "agent-g"},
            },
            {
                "models": {
                    "deepseek-flash": {"codex": "--model deepseek-v4-flash"},
                },
            },
            data_dir=os.path.join(os.path.dirname(__file__), "..", "..", "shared", "store"),
            prompt="hello task",
        )
        self.assertIsNotNone(spec)
        argv = spec["argv"]
        # Windows 宿主无 docker.exe 时经 wsl -e 桥接（direct_push._host_docker_argv）
        import shutil as _shutil
        if not (_shutil.which("docker") or _shutil.which("docker.exe")):
            self.assertTrue(
                str(argv[0]).lower().endswith(("wsl.exe", "wsl")), argv
            )
            self.assertEqual(argv[1], "-e")
            self.assertEqual(argv[2], "docker")
            self.assertEqual(argv[3], "exec")
        else:
            self.assertEqual(argv[0], "docker")
            self.assertEqual(argv[1], "exec")
        self.assertIn("codex", argv)
        self.assertIn("exec", argv)
        self.assertEqual(argv[-1], "hello task")
        mid = argv[argv.index("-m") + 1]
        self.assertEqual(mid, "deepseek-v4-flash")

    @patch("lib.adapters.frameworks.claude_launch.resolve_claude_executable", return_value=r"C:\claude.exe")
    @patch("lib.adapters.frameworks.claude_launch._platform_enabled", return_value=True)
    @patch("lib.adapters.frameworks.claude_launch.resolve_claude_platform", return_value="windows")
    def test_claude_delegates_to_direct(self, *_m):
        if sys.platform != "win32":
            self.skipTest("windows claude path")
        spec = try_build_push_direct(
            "agent-h",
            {
                "type": "claude_code",
                "models": ["deepseek-flash"],
                "push": {"cwd": r"<PROJECT_ROOT>"},
            },
            {"models": {"deepseek-flash": {"claude_code": "--model deepseek-v4-flash"}}},
            data_dir=os.path.join(os.path.dirname(__file__), "..", "..", "shared", "store"),
            prompt="ping",
        )
        self.assertIsNotNone(spec)
        self.assertTrue(spec["argv"][0].lower().endswith("claude.exe"))
        self.assertIn("deepseek-v4-flash", spec["argv"])


if __name__ == "__main__":
    unittest.main()
