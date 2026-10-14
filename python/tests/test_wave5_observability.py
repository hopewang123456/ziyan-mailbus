"""Wave 5: E9 lifecycle trace + E10 token budget alert action."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.ops.demo_chain import run_demo


class TestTaskTrace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {}}, f)
        # demo 链生成带完整生命周期的真实工单（namespace: <tmp>/demo/）
        result = run_demo(self.tmp)
        self.assertTrue(result["ok"], msg=str(result))
        self.task_id = result["task_id"]
        self.store = os.path.join(self.tmp, "demo")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_trace_replays_full_lifecycle(self):
        from lib.application.ops.task_trace import task_trace

        trace = task_trace(self.store, self.task_id)
        phases = [e["phase"] for e in trace["events"]]
        # 发起→派工→投递→执行→回执→归档 全阶段在场
        for expect in ("created", "planned", "dispatched", "delivered", "step_done", "terminal"):
            self.assertIn(expect, phases, msg=str(phases))
        self.assertEqual(trace["status"], "success")
        self.assertEqual(len(trace["steps"]), 2)
        # 时序单调（ts 升序；同秒内保持顺序）
        ts_list = [e["ts"] for e in trace["events"]]
        self.assertEqual(ts_list, sorted(ts_list))
        # 台账事件（token 佐证）入序
        self.assertTrue(any(e["source"] == "ledger" for e in trace["events"]))

    def test_unknown_task_raises(self):
        from lib.application.ops.task_trace import task_trace

        with self.assertRaises(ValueError):
            task_trace(self.store, "no-such-task")

    def test_format_text(self):
        from lib.application.ops.task_trace import format_trace_text, task_trace

        text = format_trace_text(task_trace(self.store, self.task_id))
        self.assertIn("工单回放", text)
        self.assertIn("step_done", text)


class TestBudgetAlert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({
                "agents": {},
                "mailbus_automation": {"token_budget": {"daily_est_tokens": 10}},
            }, f)
        # 预置今日台账消耗（超限）
        from lib.infra.token_ledger import record_push

        record_push(self.tmp, agent="a1", task_id="t1", prompt_chars=400)  # 100 tok

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_exceed_alerts_once(self):
        from lib.application.ops.budget_alert import check_token_budget

        out = check_token_budget(self.tmp)
        self.assertEqual(out["action"], "alerted")
        self.assertTrue(out["exceeded"])
        # alerts.json 落告警（带 Top 工单归因）
        with open(os.path.join(self.tmp, "alerts.json"), encoding="utf-8") as f:
            alerts = json.load(f)
        hits = [a for a in alerts.get("alerts", []) if a.get("type") == "token_budget_exceeded"]
        self.assertEqual(len(hits), 1)
        self.assertIn("t1", hits[0]["message"])
        # 幂等：当日第二次不重复
        out2 = check_token_budget(self.tmp)
        self.assertEqual(out2["action"], "already_alerted_today")

    def test_within_budget_no_action(self):
        tmp2 = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp2, ignore_errors=True)
        with open(os.path.join(tmp2, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {}}, f)  # 无预算
        from lib.application.ops.budget_alert import check_token_budget

        out = check_token_budget(tmp2)
        self.assertEqual(out["action"], "none")


if __name__ == "__main__":
    unittest.main()
