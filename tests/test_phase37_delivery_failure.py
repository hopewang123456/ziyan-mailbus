"""Phase 3.7 — delivery failure counting wired to scanner/pusher helper."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.dispatch.pipeline_step_failover import note_pipeline_verify_failure
from lib.tracker import TaskTracker


class TestNotePipelineVerifyFailure(unittest.TestCase):
    def test_increments_delivery_failures(self):
        with tempfile.TemporaryDirectory() as td:
            tasks = os.path.join(td, "tasks")
            os.makedirs(tasks)
            task_id = "task-fail-001"
            task = {
                "task_id": task_id,
                "status": "running",
                "chain": [{
                    "step": 1,
                    "step_id": "s1",
                    "status": "running",
                    "fsm_state": "awaiting_result",
                    "to_agent": "dali",
                    "to_person": "dali",
                }],
            }
            with open(os.path.join(tasks, f"{task_id}.json"), "w", encoding="utf-8") as f:
                json.dump(task, f)
            with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"pipeline_ops": {"max_failures_per_step": 3}}, f)
            note_pipeline_verify_failure(td, task_id, "dali", "msg-1", reason="missing_msg_results")
            updated = TaskTracker(td).get(task_id)
            self.assertEqual(updated["chain"][0].get("delivery_failures"), 1)


if __name__ == "__main__":
    unittest.main()
