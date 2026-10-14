"""E3: token ledger — per-push (incl. internal LLM) accounting, today view, attribution."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.infra.token_ledger import (
    by_task,
    daily_budget,
    extract_usage_from_result,
    record_internal_llm,
    record_push,
    record_result_usage,
    today_summary,
)


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {}}, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_push_estimated_from_prompt_chars(self):
        record_push(self.tmp, agent="a1", task_id="t1", step_id="s1",
                    framework="claude_code", trigger="dispatch", prompt_chars=400)
        s = today_summary(self.tmp)
        self.assertEqual(s["est_tokens_total"], 100)  # 400 chars / 4
        self.assertEqual(s["by_kind"]["push"], 100)
        self.assertEqual(s["by_agent"]["a1"], 100)
        self.assertEqual(s["top_tasks"][0]["task_id"], "t1")

    def test_internal_llm_and_result_usage_same_ledger(self):
        record_internal_llm(self.tmp, task_id="t1", purpose="plan", prompt_chars=200)
        record_result_usage(self.tmp, task_id="t1", step_id="s1", agent="a1",
                            usage={"input": 100, "output": 50, "total": 150})
        s = today_summary(self.tmp)
        # reported(150) + estimated(50) 都入账
        self.assertEqual(s["est_tokens_total"], 200)
        self.assertEqual(s["by_kind"]["internal_llm"], 50)
        self.assertEqual(s["by_kind"]["result_usage"], 150)
        drill = by_task(self.tmp, "t1")
        self.assertEqual(len(drill), 2)

    def test_by_task_attribution(self):
        record_push(self.tmp, agent="a1", task_id="tA", prompt_chars=100)
        record_push(self.tmp, agent="a2", task_id="tB", prompt_chars=300)
        self.assertEqual(len(by_task(self.tmp, "tB")), 1)
        self.assertEqual(by_task(self.tmp, "missing"), [])
        self.assertEqual(by_task("", "tA"), [])

    def test_budget_flag(self):
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({
                "agents": {},
                "mailbus_automation": {"token_budget": {"daily_est_tokens": 50}},
            }, f)
        self.assertEqual(daily_budget(self.tmp), 50)
        record_push(self.tmp, agent="a1", task_id="t1", prompt_chars=400)  # 100 tok
        s = today_summary(self.tmp)
        self.assertTrue(s["budget"]["exceeded"])
        self.assertEqual(s["budget"]["used_pct"], 200.0)

    def test_no_budget_by_default(self):
        record_push(self.tmp, agent="a1", prompt_chars=100)
        s = today_summary(self.tmp)
        self.assertFalse(s["budget"]["exceeded"])
        self.assertIsNone(s["budget"]["used_pct"])

    def test_extract_usage_shapes(self):
        self.assertEqual(extract_usage_from_result({"usage": {"total": 5}}), {"total": 5})
        self.assertEqual(extract_usage_from_result({"token_usage": {"total": 5}}), {"total": 5})
        self.assertIsNone(extract_usage_from_result({"summary": "done"}))


class TestHookPoints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {}}, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_step_result_write_records_reported_usage(self):
        from lib.core.a2a.step_result_io import write_step_result_file

        write_step_result_file(
            self.tmp, "tk-1", "s1",
            {"status": "completed", "conclusion": "done", "agent": "a1",
             "usage": {"input": 10, "output": 5, "total": 15}},
        )
        drill = by_task(self.tmp, "tk-1")
        self.assertEqual(len(drill), 1)
        self.assertEqual(drill[0]["kind"], "result_usage")
        self.assertEqual(drill[0]["est_tokens"], 15)
        self.assertEqual(drill[0]["source"], "reported")

    def test_internal_llm_record_call_writes_ledger(self):
        from lib.application.internal_llm.token_budget import record_call

        record_call(self.tmp, "tk-2", failed=False, purpose="plan", prompt_chars=120)
        drill = by_task(self.tmp, "tk-2")
        self.assertEqual(len(drill), 1)
        self.assertEqual(drill[0]["kind"], "internal_llm")
        self.assertEqual(drill[0]["est_tokens"], 30)

    def test_harness_spawn_records_push(self):
        from unittest import mock

        from lib.application.harness import get_harness

        harness = get_harness({"harness": {"mode": "production"}})
        with mock.patch("lib.composition.try_build_push_direct", return_value=None):
            harness.spawn("a9", {
                "data_dir": self.tmp,
                "task_id": "tk-3",
                "step_id": "s1",
                "msg_id": "msg-tk-3-s1",
                "prompt": "x" * 80,
                "framework": "none",
                "allow_no_spawn": True,
            })
        drill = by_task(self.tmp, "tk-3")
        self.assertEqual(len(drill), 1)
        self.assertEqual(drill[0]["kind"], "push")
        self.assertEqual(drill[0]["trigger"], "dispatch")
        # 估算基于完整 prompt（含追加的 contract 摘要），≥ 纯 intent 部分
        self.assertGreaterEqual(drill[0]["est_tokens"], 20)


if __name__ == "__main__":
    unittest.main()
