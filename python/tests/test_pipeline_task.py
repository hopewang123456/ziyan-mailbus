"""pipeline_task: auto_ack 与 pipeline 消息识别。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.orchestration.pipeline.task import (
    extract_task_id,
    is_pipeline_execute_message,
    pipeline_completion_block,
    should_auto_ack_message,
)


class TestPipelineTask(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "msg-results"), exist_ok=True)
        task = {
            "task_id": "game-stellar-20260617",
            "status": "running",
            "chain": [
                {"step": 1, "to_person": "agent-a", "status": "completed"},
                {"step": 2, "to_person": "agent-d", "status": "running"},
            ],
        }
        with open(os.path.join(self.tmp, "tasks", "game-stellar-20260617.json"), "w") as f:
            json.dump(task, f)

    def test_extract_task_id(self):
        self.assertEqual(extract_task_id("📋 【game-stellar-20260617】pipeline"), "game-stellar-20260617")

    def test_pipeline_execute_message(self):
        msg = {
            "to": "agent-d",
            "content": "【game-stellar-20260617】请执行",
            "type": "task",
        }
        self.assertTrue(is_pipeline_execute_message(msg, self.tmp))

    def test_should_not_auto_ack_pipeline_step(self):
        msg = {
            "to": "agent-d",
            "content": "【game-stellar-20260617】pipeline 步骤",
            "type": "task",
            "action": {"execute": True},
        }
        self.assertFalse(should_auto_ack_message(msg, self.tmp, "hermes_profile"))

    def test_should_auto_ack_notice(self):
        msg = {"content": "团队规范已更新", "type": "notice"}
        self.assertTrue(should_auto_ack_message(msg, self.tmp, "hermes_profile"))

    def test_completion_block_contains_step(self):
        content = "【game-stellar-20260617】pipeline"
        block = pipeline_completion_block(self.tmp, content, "agent-d")
        self.assertIn("pipeline_step", block)
        self.assertIn("game-stellar-20260617", block)

    def test_should_not_create_tracker_for_pipeline(self):
        from lib.application.orchestration.pipeline.task import should_create_tracker_for_send

        task = {
            "task_id": "game-stellar-20260617",
            "status": "running",
            "chain": [{"step": 1, "to_person": "agent-a", "status": "running", "planned_agents": ["agent-d"]}],
        }
        with open(os.path.join(self.tmp, "tasks", "game-stellar-20260617.json"), "w") as f:
            json.dump(task, f)
        self.assertFalse(
            should_create_tracker_for_send("【game-stellar-20260617】Step1", self.tmp)
        )

    def test_verify_delivery_missing_results(self):
        from lib.application.orchestration.pipeline.task import verify_pipeline_step_delivery

        task = {
            "task_id": "game-stellar-20260617",
            "status": "running",
            "chain": [{"step": 2, "to_person": "agent-d", "status": "running"}],
        }
        with open(os.path.join(self.tmp, "tasks", "game-stellar-20260617.json"), "w") as f:
            json.dump(task, f)
        ok, reason = verify_pipeline_step_delivery(
            self.tmp, "agent-d", {"content": "【game-stellar-20260617】", "task_id": "game-stellar-20260617"}
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_msg_results")


if __name__ == "__main__":
    unittest.main()
