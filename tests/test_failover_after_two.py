"""Failover 连续失败 2 次触发改派测试。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.orchestration.dispatch.pipeline_step_failover import (
    max_failures_per_step,
    record_step_delivery_failure,
    should_failover_after_failures,
)


class TestFailoverAfterTwo(unittest.TestCase):
    def test_max_failures_from_config(self):
        cfg = {"pipeline_ops": {"role_failover": {"max_failures_per_step": 2}}}
        self.assertEqual(max_failures_per_step(cfg), 2)

    def test_record_triggers_on_second_failure(self):
        step = {}
        cfg = {"pipeline_ops": {"max_failures_per_step": 2}}
        self.assertFalse(record_step_delivery_failure(step, cfg))
        self.assertTrue(record_step_delivery_failure(step, cfg))
        self.assertEqual(step["delivery_failures"], 2)
        self.assertTrue(should_failover_after_failures(step, cfg))

    def test_default_threshold_is_two(self):
        step = {"delivery_failures": 1}
        self.assertFalse(should_failover_after_failures(step, {}))
        step["delivery_failures"] = 2
        self.assertTrue(should_failover_after_failures(step, {}))


if __name__ == "__main__":
    unittest.main()
