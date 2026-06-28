"""recover --continue 测试。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.task_fsm import TaskFsmState, ensure_fsm
from lib.task_recover import apply_cancel_task, recover_continue
from lib.utils import json_read, json_write


class TestRecoverContinue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for sub in ("tasks", "inbox/dali", "msg-files", "work-orders", "locks"):
            os.makedirs(os.path.join(self.tmp, *sub.split("/")), exist_ok=True)
        json_write(os.path.join(self.tmp, "config.json"), {
            "agents": {"dali": {"type": "opencode"}},
        })
        json_write(os.path.join(self.tmp, "inbox", "dali", "inbox.json"), {
            "agent": "dali", "messages": [],
        })
        self.tid = "recover-test"
        task = {
            "task_id": self.tid,
            "status": "paused",
            "assignee": "dali",
            "fsm": {"state": TaskFsmState.PAUSED.value, "history": []},
            "chain": [{
                "step": 1,
                "step_id": "s1",
                "status": "running",
                "fsm_state": "awaiting_result",
                "to_agent": "dali",
                "to_person": "dali",
                "to_role": "编码",
                "summary": "继续实现",
            }],
        }
        json_write(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), task)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_recover_paused_task(self):
        out = recover_continue(self.tmp, self.tid, reason="test")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("step_id"), "s1")
        task = json_read(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), {})
        ensure_fsm(task)
        self.assertEqual(task["fsm"]["state"], TaskFsmState.EXECUTING.value)
        wo = os.path.join(self.tmp, "work-orders", self.tid, "step-s1.md")
        self.assertTrue(os.path.isfile(wo) or os.listdir(os.path.join(self.tmp, "msg-files")))

    def test_cancel_task(self):
        out = apply_cancel_task(self.tmp, self.tid, reason="user_cancel")
        self.assertTrue(out.get("ok"))
        task = json_read(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), {})
        self.assertEqual(task["fsm"]["state"], TaskFsmState.CANCELLED.value)


if __name__ == "__main__":
    unittest.main()
