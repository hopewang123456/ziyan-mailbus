"""pipeline_results 框架层单测。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.orchestration.pipeline.results import (
    read_result_from_paths,
    result_paths_to_try,
    step_result_path,
)
from lib.adapters.orchestration.task_fsm import write_step_result
from lib.infra.utils import json_write


class TestPipelineResults(unittest.TestCase):
    def test_write_step_result_only(self):
        with tempfile.TemporaryDirectory() as td:
            json_write(os.path.join(td, "config.json"), {})
            step = {"step": 1, "step_id": "s1", "started_at": "2026-06-25T12:00:00+08:00"}
            write_step_result(
                td, "task-a", step,
                {"agent": "agent-i", "conclusion": "done"},
                immediate_advance=False,
            )
            self.assertTrue(os.path.isfile(step_result_path(td, "task-a", "s1")))
            self.assertFalse(os.path.isfile(os.path.join(td, "msg-results", "task-a.json")))

    def test_result_paths_to_try_step_only(self):
        with tempfile.TemporaryDirectory() as td:
            step = {"step_id": "s2"}
            paths = result_paths_to_try(td, "t1", step, config={"mailbus_automation": {}})
            self.assertEqual(paths, [step_result_path(td, "t1", "s2")])
            self.assertFalse(any(p.endswith("t1.json") for p in paths))

    def test_read_result_from_paths_order(self):
        with tempfile.TemporaryDirectory() as td:
            step_path = step_result_path(td, "t1", "s1")
            os.makedirs(os.path.dirname(step_path), exist_ok=True)
            json_write(step_path, {"source": "step"})
            other = os.path.join(td, "msg-results", "t1", "other.json")
            json_write(other, {"source": "other"})
            data = read_result_from_paths([step_path, other])
            self.assertEqual(data.get("source"), "step")


if __name__ == "__main__":
    unittest.main()
