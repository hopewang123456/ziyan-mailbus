"""token_budget 单元测试（纯逻辑，无文件 IO）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.token_budget import (
    effective_scan_interval_seconds,
    load_token_budget,
    measure_mailbus_activity,
)


class TestTokenBudget(unittest.TestCase):
    def test_load_defaults(self):
        tb = load_token_budget({"cli_msg_max_chars": 500})
        self.assertEqual(tb["cli_msg_max_chars"], 500)
        self.assertEqual(tb["scan_interval_idle_seconds"], 300)

    def test_effective_scan_interval(self):
        cfg = {"token_budget": {"scan_interval_idle_seconds": 600, "scan_interval_active_seconds": 120}}
        self.assertEqual(effective_scan_interval_seconds(cfg, {"level": "idle"}), 600)
        self.assertEqual(effective_scan_interval_seconds(cfg, {"level": "active"}), 120)
        self.assertEqual(effective_scan_interval_seconds(cfg, {"level": "urgent"}), 120)

    def test_measure_idle_empty_dir(self):
        import tempfile
        td = tempfile.mkdtemp()
        cfg = {"agents": {}}
        act = measure_mailbus_activity(td, {}, cfg)
        self.assertEqual(act["level"], "idle")
        self.assertEqual(act["pending_messages"], 0)


if __name__ == "__main__":
    unittest.main()
