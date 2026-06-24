"""Step result API + immediate pipeline dispatch tests."""

import json
import os
import tempfile
import unittest

from lib.task_fsm import (
    ensure_fsm,
    get_active_step,
    write_step_result,
    archive_step_result_for_retry,
)
from lib.pipeline_trigger import trigger_task
from lib.utils import json_write, resolve_paths


class TestStepResultPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "dali"), exist_ok=True)
        json_write(os.path.join(self.tmp, "inbox", "dali", "inbox.json"), {"agent": "dali", "messages": []})
        json_write(os.path.join(self.tmp, "config.json"), {
            "agents": {"dali": {"cli": "echo"}},
            "mailbus_automation": {"immediate_pipeline_dispatch": True},
        })
        self.task = {
            "task_id": "t-immediate-1",
            "status": "running",
            "chain": [{
                "step": 1,
                "step_id": "s1",
                "to_person": "dali",
                "to_role": "开发者",
                "fsm_state": "awaiting_result",
                "status": "running",
            }],
            "fsm": {"state": "executing", "active_step_id": "s1"},
        }
        json_write(os.path.join(self.tmp, "tasks", "t-immediate-1.json"), self.task)

    def test_archive_retry_clears_result(self):
        task = ensure_fsm(dict(self.task))
        step = get_active_step(task)
        write_step_result(self.tmp, "t-immediate-1", step, {
            "conclusion": "done", "summary": "x", "agent": "dali",
        }, immediate_advance=False)
        result = {"conclusion": "done", "summary": "bad"}
        path = archive_step_result_for_retry(self.tmp, "t-immediate-1", step, result)
        self.assertTrue(path and os.path.isfile(path))

    def test_trigger_task_no_result(self):
        out = trigger_task(self.tmp, "t-immediate-1", {"dali": {}}, resolve_paths(self.tmp))
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("skipped"), "no_result")


if __name__ == "__main__":
    unittest.main()
