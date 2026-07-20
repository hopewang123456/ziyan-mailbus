"""pipeline_results 框架层单测。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.pipeline_results import (
    find_legacy_result_file,
    legacy_mirror_enabled,
    legacy_read_enabled,
    read_result_from_paths,
    result_paths_to_try,
    step_result_path,
)
from lib.task_fsm import write_step_result
from lib.utils import json_write


class TestPipelineResults(unittest.TestCase):
    def test_legacy_mirror_default_off(self):
        self.assertFalse(legacy_mirror_enabled({}))

    def test_legacy_read_default_on(self):
        self.assertTrue(legacy_read_enabled({}))

    def test_write_no_legacy_mirror_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            json_write(os.path.join(td, "config.json"), {})
            step = {"step": 1, "step_id": "s1", "started_at": "2026-06-25T12:00:00+08:00"}
            write_step_result(
                td, "task-a", step,
                {"agent": "dali", "conclusion": "done"},
                immediate_advance=False,
            )
            self.assertTrue(os.path.isfile(step_result_path(td, "task-a", "s1")))
            self.assertFalse(os.path.isfile(os.path.join(td, "msg-results", "task-a.json")))

    def test_result_paths_to_try_includes_step_then_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            step = {"step_id": "s2"}
            paths = result_paths_to_try(td, "t1", step, config={"mailbus_automation": {}})
            self.assertIn(step_result_path(td, "t1", "s2"), paths)
            self.assertTrue(any(p.endswith("t1.json") for p in paths))

    def test_find_legacy_result_file(self):
        with tempfile.TemporaryDirectory() as td:
            leg = os.path.join(td, "msg-results", "t1.json")
            os.makedirs(os.path.dirname(leg), exist_ok=True)
            json_write(leg, {"ok": True})
            self.assertEqual(find_legacy_result_file(td, "t1"), leg)
            self.assertIsNone(find_legacy_result_file(td, "missing"))

    def test_read_result_from_paths_order(self):
        with tempfile.TemporaryDirectory() as td:
            step_path = step_result_path(td, "t1", "s1")
            os.makedirs(os.path.dirname(step_path), exist_ok=True)
            json_write(step_path, {"source": "step"})
            leg = os.path.join(td, "msg-results", "t1.json")
            json_write(leg, {"source": "legacy"})
            data = read_result_from_paths([step_path, leg])
            self.assertEqual(data.get("source"), "step")


if __name__ == "__main__":
    unittest.main()
