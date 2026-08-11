"""A2A mapper 与金样例 fixture 测试（零 LLM / 零 HTTP）。"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.a2a.a2a_mapper import from_a2a_task, to_a2a_message
from tests.test_helpers import load_golden_a2a_path


class TestGoldenFixtureShape(unittest.TestCase):
    def test_all_paths_loadable(self):
        for letter in "abcd":
            data = load_golden_a2a_path(letter)
            self.assertEqual(data.get("schema"), "mailbus-golden-a2a-path-v1")
            self.assertEqual(data.get("path"), letter)

    def test_path_a_has_wire_and_step_result(self):
        data = load_golden_a2a_path("a")
        self.assertIn("canonical_dispatch", data)
        self.assertIn("wire", data)
        self.assertIn("canonical_step_result", data)
        sr = data["canonical_step_result"]
        for field in ("task_id", "step_id", "agent", "conclusion", "transport_used"):
            self.assertIn(field, sr)

    def test_path_b_retries_exhausted(self):
        data = load_golden_a2a_path("b")
        audit = data["transport_audit"]
        self.assertTrue(audit.get("a2a_retries_exhausted"))
        attempts = audit.get("transport_attempts") or []
        a2a_fails = [a for a in attempts if a.get("channel") == "a2a_standard" and a.get("outcome") == "fail"]
        self.assertEqual(len(a2a_fails), 3)

    def test_path_d_no_a2a(self):
        data = load_golden_a2a_path("d")
        self.assertFalse(data["scenario"].get("can_deliver_a2a", True))
        sr = data["canonical_step_result"]
        self.assertEqual(sr.get("normalized_from"), "opencode_replies")


class TestA2AMapper(unittest.TestCase):
    def test_to_a2a_message_role_user(self):
        data = load_golden_a2a_path("a")
        dispatch = data["canonical_dispatch"]
        msg = to_a2a_message(dispatch)
        self.assertEqual(msg["role"], "ROLE_USER")
        meta = msg["metadata"]["mailbus"]
        self.assertEqual(meta["taskId"], "feat-auth-001")
        self.assertEqual(meta["stepId"], "s1")
        self.assertEqual(meta["toAgentId"], "lingzhao")

    def test_from_a2a_task_matches_golden_a(self):
        data = load_golden_a2a_path("a")
        task = data["wire"]["get_task_terminal"]
        expected = data["canonical_step_result"]
        got = from_a2a_task(
            task,
            task_id=expected["task_id"],
            step_id=expected["step_id"],
            agent=expected["agent"],
            role_type=expected["role_type"],
        )
        for key in (
            "task_id",
            "step_id",
            "agent",
            "role_type",
            "conclusion",
            "summary",
            "source",
            "transport_used",
            "a2a_task_id",
        ):
            self.assertEqual(got.get(key), expected.get(key), msg=key)

    def test_resolve_message_role_agent(self):
        data = load_golden_a2a_path("c")
        msg = data["wire"]["resolve_send_message"]["params"]["message"]
        self.assertEqual(msg["role"], "ROLE_AGENT")
        self.assertEqual(msg["metadata"]["mailbus"]["agentId"], "lingzhao")


if __name__ == "__main__":
    unittest.main()
