"""Wave 2 E-wizard: demo API endpoints (run/clean/trace) handler baseline."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeHandler:
    def __init__(self, data_dir: str, body: dict | None = None):
        self.data_dir = data_dir
        self.body = body or {}
        self.sent: list[tuple[dict, int]] = []

    def _read_post_body(self) -> dict:
        return self.body

    def _send_json(self, payload: dict, status: int = 200) -> None:
        self.sent.append((payload, status))


class TestDemoApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {}}, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_clean_trace_lifecycle(self):
        from lib.api.handlers_system import handle_demo_clean, handle_demo_run, handle_demo_trace

        # trace: 无演示 → inactive
        h = _FakeHandler(self.tmp)
        handle_demo_trace(h)
        payload, status = h.sent[0]
        self.assertEqual(status, 200)
        self.assertFalse(payload["active"])

        # run：完整闭环 + 叙事行
        h = _FakeHandler(self.tmp, body={})
        handle_demo_run(h)
        payload, status = h.sent[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"], msg=str(payload))
        self.assertEqual(payload["task_status"], "success")
        self.assertTrue(any("完整闭环" in ln for ln in payload["lines"]))

        # trace：active + 叙事
        h = _FakeHandler(self.tmp)
        handle_demo_trace(h)
        payload, _ = h.sent[0]
        self.assertTrue(payload["active"])
        self.assertEqual(payload["task_id"][:5], "demo-")
        self.assertTrue(payload["lines"])

        # clean：清除后 inactive
        h = _FakeHandler(self.tmp)
        handle_demo_clean(h)
        payload, _ = h.sent[0]
        self.assertTrue(payload["removed"])
        h = _FakeHandler(self.tmp)
        handle_demo_trace(h)
        self.assertFalse(h.sent[0][0]["active"])


if __name__ == "__main__":
    unittest.main()
