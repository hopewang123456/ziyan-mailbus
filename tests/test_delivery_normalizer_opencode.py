"""OpenCode Delivery Normalizer 三源测试。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.delivery_normalizer import (
    load_delivery_config,
    normalize_from_reply_record,
    normalize_opencode_deliveries,
)
from lib.adapters.orchestration.task_fsm import read_step_result, step_result_path
from lib.utils import json_write


class TestDeliveryNormalizerOpencode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "replies"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "patches"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "dali"), exist_ok=True)
        self.tid = "game-courier-norm"
        json_write(os.path.join(self.tmp, "config.json"), {
            "agents": {"dali": {"type": "opencode"}},
            "framework_delivery": {"opencode": {"enabled": True}},
        })
        task = {
            "task_id": self.tid,
            "status": "running",
            "assignee": "dali",
            "chain": [{
                "step": 1,
                "step_id": "s1",
                "status": "running",
                "to_agent": "dali",
                "to_person": "dali",
                "to_role": "编码",
            }],
        }
        json_write(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), task)
        json_write(os.path.join(self.tmp, "inbox", "dali", "inbox.json"), {
            "agent": "dali",
            "messages": [{
                "id": "msg-norm-1",
                "task_id": self.tid,
                "content": f"【{self.tid}】 step_id=s1",
                "state": "processing",
            }],
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_delivery_config_defaults(self):
        cfg = load_delivery_config({})
        self.assertTrue(cfg.get("enabled"))
        self.assertIn("replies", cfg.get("sources", []))

    def test_reply_to_step_result(self):
        reply = {
            "agent": "dali",
            "msg_ids": ["msg-norm-1"],
            "reply": "已完成 courier 模块实现与单测",
            "patch": os.path.join(self.tmp, "patches", "0001-fix.patch"),
            "timestamp": "2026-06-26T10:00:00+08:00",
        }
        patch_path = os.path.join(self.tmp, "patches", "0001-fix.patch")
        with open(patch_path, "w", encoding="utf-8") as f:
            f.write("diff --git a/x b/x\n")
        n = normalize_from_reply_record(self.tmp, "dali", reply)
        self.assertEqual(n, 1)
        step = {"step_id": "s1"}
        result = read_step_result(self.tmp, self.tid, step)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("conclusion"), "done")
        self.assertTrue(result.get("normalized"))
        self.assertTrue(os.path.isfile(step_result_path(self.tmp, self.tid, "s1")))

    def test_normalize_opencode_deliveries_batch(self):
        json_write(os.path.join(self.tmp, "replies", "dali.json"), {
            "agent": "dali",
            "msg_ids": ["msg-norm-1"],
            "reply": "done with patch",
        })
        stats = normalize_opencode_deliveries(
            self.tmp, {"dali": {"type": "opencode"}},
        )
        self.assertGreaterEqual(stats["total"], 1)


if __name__ == "__main__":
    unittest.main()
