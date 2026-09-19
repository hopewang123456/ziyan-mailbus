"""E1 三段式测试连接 — probe / discover preview / smoke-ack service."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.ops.connection_test import (
    format_connection_text,
    run_connection_test,
)


class _Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cfg = {
            "agents": {
                "demo-a": {
                    "type": "none", "name": "演示A",
                    "instance_id": "inst-none", "enabled": True,
                },
            },
            "agent_instances": {
                "inst-none": {
                    "id": "inst-none", "type": "none", "run_target": "windows",
                    "install_path": "", "role_ids": ["demo-a"], "enabled": True,
                },
            },
        }
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestProbeAndDiscover(_Store):
    def test_none_framework_probe_green_discover_skipped(self):
        report = run_connection_test(self.tmp, "inst-none", auto_load_roles=False, ack_timeout_sec=1)
        probe = report["stages"]["probe"]
        self.assertTrue(probe["ok"])
        disc = report["stages"]["discover"]
        self.assertTrue(disc["ok"])
        self.assertEqual(disc["count"], 0)

    def test_unknown_instance_raises(self):
        with self.assertRaises(ValueError):
            run_connection_test(self.tmp, "no-such", auto_load_roles=False)


class TestSmokeAck(_Store):
    def test_smoke_waits_for_agent_ack(self):
        def _ack_later():
            time.sleep(1.0)
            inbox_dir = os.path.join(self.tmp, "inbox", "demo-a")
            # wait for inbox message to appear
            for _ in range(50):
                p = os.path.join(inbox_dir, "inbox.json")
                if os.path.isfile(p):
                    break
                time.sleep(0.1)
            with open(p, encoding="utf-8") as f:
                msgs = json.load(f).get("messages") or []
            smoke = [m["id"] for m in msgs if str(m["id"]).startswith("smoke-")]
            with open(os.path.join(inbox_dir, "ack.json"), "w", encoding="utf-8") as f:
                json.dump([{"action": "ack", "msg_id": smoke[-1], "agent": "demo-a"}], f)

        threading.Thread(target=_ack_later, daemon=True).start()
        report = run_connection_test(
            self.tmp, "inst-none", ack_timeout_sec=15, auto_load_roles=False,
        )
        smoke = report["stages"]["smoke"]
        self.assertTrue(smoke["ok"], msg=str(smoke))
        self.assertEqual(smoke["target"], "demo-a")
        self.assertTrue(report["ok"])

    def test_smoke_red_on_no_ack(self):
        report = run_connection_test(
            self.tmp, "inst-none", ack_timeout_sec=1, auto_load_roles=False,
        )
        smoke = report["stages"]["smoke"]
        self.assertFalse(smoke["ok"])
        self.assertFalse(report["ok"])
        text = format_connection_text(report)
        self.assertIn("缺口清单", text)
        self.assertIn("未接通", text)


class TestFormat(unittest.TestCase):
    def test_format_lists_gaps(self):
        report = {
            "instance_id": "i1", "framework": "codex", "run_target": "docker",
            "ok": False,
            "roles_loaded": ["r1"],
            "stages": {
                "probe": {"ok": False, "detail": "not found", "platform": "docker"},
                "discover": {"ok": True, "count": 2, "roles": []},
                "smoke": {"ok": False, "detail": "timeout waiting for ack",
                          "target": "r1", "elapsed_sec": 90},
            },
        }
        text = format_connection_text(report)
        self.assertIn("✗", text)
        self.assertIn("已自动上架角色: r1", text)
        self.assertIn("缺口清单", text)
        self.assertIn("probe", text)


if __name__ == "__main__":
    unittest.main()
