"""E2 batch 2: DLQ (dead-letter queue) + forward loop guard."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.results.ack_handler import process_forward
from lib.infra.dlq import dlq_append, dlq_recent, forward_hop_check


class TestDlq(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_and_recent_roundtrip(self):
        dlq_append(self.tmp, {"reason": "push_exhausted", "msg_id": "m-1",
                              "agent": "a1", "error": "no cli", "snapshot": {"content": "x"}})
        dlq_append(self.tmp, {"reason": "forward_loop", "msg_id": "m-2", "agent": "b1"})
        records = dlq_recent(self.tmp, 10)
        self.assertEqual(len(records), 2)
        self.assertEqual({r["msg_id"] for r in records}, {"m-1", "m-2"})

    def test_recent_empty_store(self):
        self.assertEqual(dlq_recent(self.tmp, 5), [])
        self.assertEqual(dlq_recent("", 5), [])


class TestForwardLoopGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {"a": {"type": "none"}, "b": {"type": "none"}}}, f)
        for agent in ("a", "b"):
            os.makedirs(os.path.join(self.tmp, "inbox", agent), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _forward(self, root: str, frm: str = "a", to: str = "b"):
        return process_forward(self.tmp, {
            "action": "forward",
            "original_msg_id": root,
            "from": frm,
            "to": to,
            "type": "task",
            "content": f"fwd {root}",
        })

    def test_hops_below_limit_pass(self):
        self.assertTrue(self._forward("root-1"))
        self.assertTrue(self._forward("root-1", frm="b", to="a"))
        inbox = json.load(open(os.path.join(self.tmp, "inbox", "a", "inbox.json"), encoding="utf-8"))
        self.assertTrue(any(m.get("original_msg_id") == "root-1" for m in inbox["messages"]))

    def test_loop_rejected_at_limit_with_dlq(self):
        # max 默认 8：前 8 跳放行，第 9 跳拒转
        for i in range(8):
            frm, to = ("a", "b") if i % 2 == 0 else ("b", "a")
            self.assertTrue(self._forward("root-2", frm=frm, to=to), f"hop {i+1} should pass")
        allowed, hops = forward_hop_check(self.tmp, "root-2", max_hops=8)
        self.assertFalse(allowed)
        self.assertEqual(hops, 9)
        self.assertFalse(self._forward("root-2"))  # 第 9 跳实际拒转
        records = dlq_recent(self.tmp, 5)
        self.assertTrue(any(r["reason"] == "forward_loop" and r["msg_id"] == "root-2" for r in records))

    def test_limit_override(self):
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({
                "agents": {"a": {"type": "none"}, "b": {"type": "none"}},
                "mailbus_automation": {"forward_hops": {"max": 2}},
            }, f)
        self.assertTrue(self._forward("root-3"))
        self.assertTrue(self._forward("root-3", frm="b", to="a"))
        self.assertFalse(self._forward("root-3"))  # 第 3 跳超 max=2

    def test_no_root_forward_passes(self):
        self.assertTrue(self._forward(""))


if __name__ == "__main__":
    unittest.main()
