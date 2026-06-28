"""task_interrupt + human_queue resolve 路由。"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.human_queue import enqueue, load_queue
from lib.human_queue_resolve import resolve_human_queue_item
from lib.task_interrupt import detect_interrupted_tasks
from lib.utils import json_write


class TestTaskInterrupt(unittest.TestCase):
    def test_detect_flags_inactive_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents = {"dali": {"type": "opencode", "inbox": f"{tmp}/inbox/dali"}}
            os.makedirs(agents["dali"]["inbox"], exist_ok=True)
            task = {
                "task_id": "t-interrupt-001",
                "status": "running",
                "summary": "test",
                "fsm": {"state": "executing", "priority": 50, "history": []},
                "chain": [{
                    "step": 1,
                    "step_id": "step-1-1",
                    "to_person": "dali",
                    "fsm_state": "in_progress",
                    "status": "running",
                    "started_at": "2020-01-01T00:00:00+00:00",
                }],
            }
            os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
            json_write(os.path.join(tmp, "tasks", "t-interrupt-001.json"), task)
            with patch("lib.task_interrupt.agent_cli_active_for", return_value=False):
                flagged = detect_interrupted_tasks(tmp, agents, min_step_age=0)
            self.assertEqual(len(flagged), 1)
            self.assertEqual(flagged[0]["task_id"], "t-interrupt-001")
            reloaded = json.load(open(os.path.join(tmp, "tasks", "t-interrupt-001.json"), encoding="utf-8"))
            self.assertTrue(reloaded.get("interrupted"))


class TestHumanQueueResolve(unittest.TestCase):
    def test_resolve_closes_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_write(os.path.join(tmp, "human-queue.json"), {
                "version": "1.0.0", "updated_at": "2026-06-26T00:00:00+08:00", "items": [],
            })
            hid = enqueue(tmp, {
                "type": "workflow_gate",
                "task_id": "missing-task",
                "gate_id": "test_gate",
                "title": "test",
            })
            item, side = resolve_human_queue_item(tmp, hid, {
                "decision": "approved",
                "reviewer": "test",
                "comment": "ok",
            })
            self.assertIsNotNone(item)
            self.assertEqual(item["status"], "approved")
            doc = load_queue(tmp)
            self.assertEqual(doc["items"][0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
