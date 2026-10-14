"""watchdog_runner — launch queue 处理逻辑测试。"""
from __future__ import annotations

import os
import tempfile
import unittest

from lib.adapters.plane.watchdog_runner import _launch_mode_for, _log


class TestWatchdogRunner(unittest.TestCase):
    def test_launch_mode_for(self) -> None:
        self.assertEqual(_launch_mode_for("echo hi", "background"), "background")
        self.assertEqual(_launch_mode_for("echo hi", ""), "background")
        self.assertEqual(_launch_mode_for("echo hi", "interactive"), "interactive")
        self.assertEqual(_launch_mode_for("docker exec -it bash", ""), "interactive")
        self.assertEqual(_launch_mode_for("openclaw tui", ""), "interactive")
        self.assertEqual(_launch_mode_for("powershell -NoExit x", ""), "interactive")
        self.assertEqual(_launch_mode_for("echo hi", "  "), "background")

    def test_log_no_crash(self) -> None:
        _log("hello watchdog")  # 仅验证不抛异常

    def test_queue_dir_creation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            qdir = os.path.join(td, "launch-queue")
            os.makedirs(qdir, exist_ok=True)
            self.assertTrue(os.path.isdir(qdir))


if __name__ == "__main__":
    unittest.main()
