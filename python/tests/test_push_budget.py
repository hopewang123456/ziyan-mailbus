"""E2: per-task push budget circuit breaker — token 黑洞熔断."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.orchestration.automation import (
    bump_push_count,
    push_budget_blocked,
    push_gate,
)


class TestPushGate(unittest.TestCase):
    def _task(self, used: int) -> dict:
        t = {"task_id": "t1", "automation": {"pushes": {"count": used}}}
        return t

    def test_default_limit_six(self):
        cfg = {"mailbus_automation": {}}
        self.assertEqual(push_gate(self._task(0), cfg), (True, 0, 6))
        self.assertEqual(push_gate(self._task(5), cfg), (True, 5, 6))
        self.assertEqual(push_gate(self._task(6), cfg), (False, 6, 6))

    def test_limit_override(self):
        cfg = {"mailbus_automation": {"push_limits": {"per_task": 2}}}
        self.assertEqual(push_gate(self._task(2), cfg), (False, 2, 2))

    def test_bump_increments(self):
        t = self._task(0)
        self.assertEqual(bump_push_count(t), 1)
        self.assertEqual(bump_push_count(t), 2)
        self.assertEqual(t["automation"]["pushes"]["count"], 2)


class TestBudgetBreak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {"a1": {"type": "none"}}}, f)
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        self.task = {
            "task_id": "bt-1",
            "status": "running",
            "chain": [{"step": 1, "step_id": "s1", "to_agent": "a1",
                       "fsm_state": "queued", "status": "running"}],
            "automation": {"pushes": {"count": 6}},
        }
        with open(os.path.join(self.tmp, "tasks", "bt-1.json"), "w", encoding="utf-8") as f:
            json.dump(self.task, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_blocked_and_human_queue_on_exceed(self):
        broke = push_budget_blocked(self.task, self.tmp)
        self.assertTrue(broke)
        self.assertEqual(self.task["status"], "blocked")
        self.assertIn("push_budget_exceeded", self.task["fsm"]["reason"])
        hq_path = os.path.join(self.tmp, "human-queue.json")
        self.assertTrue(os.path.isfile(hq_path))
        with open(hq_path, encoding="utf-8") as f:
            hq = json.load(f)
        entries = hq if isinstance(hq, list) else hq.get("items") or []
        self.assertTrue(any("bt-1" in json.dumps(e) for e in entries))

    def test_within_budget_no_break(self):
        self.task["automation"]["pushes"]["count"] = 2
        self.assertFalse(push_budget_blocked(self.task, self.tmp))
        self.assertEqual(self.task["status"], "running")


class TestFirstStepBudget(unittest.TestCase):
    def test_first_step_respects_budget(self):
        from lib.application.orchestration.router import dispatch as router_dispatch

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {"a1": {"type": "none"}}}, f)
        os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
        task = {
            "task_id": "fb-1", "status": "running",
            "chain": [{"step": 1, "step_id": "s1", "to_agent": "a1", "to_person": "a1",
                       "fsm_state": "queued", "status": "running"}],
            "automation": {"pushes": {"count": 6}},
        }
        with open(os.path.join(tmp, "tasks", "fb-1.json"), "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False)

        with mock.patch.object(router_dispatch, "dispatch_fsm_step") as df:
            ok = router_dispatch.dispatch_first_step(tmp, task)
        self.assertFalse(ok)
        df.assert_not_called()  # 预算超限 → 不派发,直接熔断
        with open(os.path.join(tmp, "tasks", "fb-1.json"), encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["status"], "blocked")

    def test_first_step_bumps_count_on_success(self):
        from lib.application.orchestration.router import dispatch as router_dispatch

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {"a1": {"type": "none"}}}, f)
        os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
        task = {
            "task_id": "ok-1", "status": "running",
            "fsm": {"state": "executing"},
            "chain": [{"step": 1, "step_id": "s1", "to_agent": "a1", "to_person": "a1",
                       "fsm_state": "queued", "status": "running"}],
        }
        with open(os.path.join(tmp, "tasks", "ok-1.json"), "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False)

        with mock.patch.object(router_dispatch, "dispatch_fsm_step", return_value=True):
            ok = router_dispatch.dispatch_first_step(tmp, task)
        self.assertTrue(ok)
        self.assertEqual(task["automation"]["pushes"]["count"], 1)
        with open(os.path.join(tmp, "tasks", "ok-1.json"), encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["automation"]["pushes"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
