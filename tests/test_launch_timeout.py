"""launch API 超时 — Codex browser 冷启动需 >30s。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.api.handlers_system import _launch_script_timeout  # noqa: E402


class LaunchScriptTimeoutTest(unittest.TestCase):
    def test_browser_timeout_covers_codex_cold_start(self):
        self.assertGreaterEqual(_launch_script_timeout("browser"), 120)

    def test_cli_stays_short(self):
        self.assertEqual(_launch_script_timeout("cli"), 30)

    def test_desktop_timeout(self):
        self.assertEqual(_launch_script_timeout("desktop"), 90)


if __name__ == "__main__":
    unittest.main()
