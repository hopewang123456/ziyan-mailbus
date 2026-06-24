"""Automation config tests."""

import os
import sys
import tempfile
import unittest

from lib.automation import (
    gate_requires_human,
    max_retry_attempts,
    should_auto_approve_plan,
    test_fail_auto_to_dev,
)
from lib.utils import json_write


class TestAutomation(unittest.TestCase):
    def test_auto_approve_plan_s_tier(self):
        cfg = {"mailbus_automation": {"auto_approve": {"plan_tiers": ["S"]}}}
        self.assertTrue(should_auto_approve_plan({"tier": "S"}, cfg))
        self.assertFalse(should_auto_approve_plan({"tier": "M"}, cfg))

    def test_test_fail_auto_to_dev(self):
        cfg = {"mailbus_automation": {"auto_retry": {"test_fail_to_dev": {"enabled": True, "tiers": ["S", "M"]}}}}
        self.assertTrue(test_fail_auto_to_dev({"tier": "M"}, cfg))

    def test_always_human_gate(self):
        cfg = {"mailbus_automation": {"always_human": ["publish_go"]}}
        self.assertTrue(gate_requires_human("publish_go", cfg))

    def test_max_retry(self):
        cfg = {"mailbus_automation": {"auto_retry": {"test_fail_to_dev": {"max_attempts": 3}}}}
        self.assertEqual(max_retry_attempts({}, cfg), 3)


if __name__ == "__main__":
    unittest.main()
