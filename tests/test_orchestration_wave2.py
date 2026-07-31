"""Wave2 orchestration + budget FSM tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.adapters.orchestration.budget import (
    BUDGET_AWAITING,
    BUDGET_PAUSED,
    BUDGET_RUNNING,
    FileBudgetMeter,
)
from lib.adapters.orchestration.fsm import TaskFsmAdapter
from lib.domain.errors import PAUSE_REASON_BUDGET


class TestBudgetMeterFsm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name
        Path(self.data, "config.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_spend_enters_awaiting(self):
        m = FileBudgetMeter(self.data)
        cfg = {"mailbus_chains": {"daily_budget_cny": 10}}
        st = m.record_spend(10, cfg)
        self.assertEqual(st["fsm_state"], BUDGET_AWAITING)
        self.assertTrue(st["awaiting_ollama_decision"])

    def test_no_reply_pauses(self):
        m = FileBudgetMeter(self.data)
        m.record_spend(30, {"mailbus_chains": {"daily_budget_cny": 30}})
        st = m.apply_ollama_decision(None, {})
        self.assertEqual(st["fsm_state"], BUDGET_PAUSED)
        self.assertTrue(st["paused"])

    def test_ollama_yes_resumes_meter(self):
        m = FileBudgetMeter(self.data)
        m.apply_ollama_decision(None, {})
        st = m.apply_ollama_decision(True, {})
        self.assertEqual(st["fsm_state"], BUDGET_RUNNING)
        self.assertTrue(st.get("force_ollama"))


class TestTaskFsmRetry(unittest.TestCase):
    def test_bump_retry_on_task_json(self):
        fsm = TaskFsmAdapter()
        task = {"task_id": "t1", "status": "running", "chain": [{"step": 1, "step_id": "s1", "status": "running"}]}
        n1 = fsm.bump_retry(task, step_id="s1")
        n2 = fsm.bump_retry(task, step_id="s1")
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 2)
        self.assertEqual(task["fsm"]["retries"]["s1"], 2)
        self.assertEqual(task["chain"][0]["retry_count"], 2)


class TestMediatorBudgetPause(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        (self.data / "config.json").write_text("{}", encoding="utf-8")
        tasks = self.data / "tasks"
        tasks.mkdir()
        task = {
            "task_id": "chain-1",
            "status": "running",
            "chain": [{"step": 1, "step_id": "s1", "status": "running", "to_person": "a"}],
            "fsm": {"state": "executing"},
        }
        (tasks / "chain-1.json").write_text(json.dumps(task), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_decision_none_pauses_tasks(self):
        from lib.application.orchestration.mediator import apply_budget_decision

        st = apply_budget_decision(str(self.data), None, {})
        self.assertEqual(st["fsm_state"], BUDGET_PAUSED)
        self.assertGreaterEqual(st.get("tasks_paused", 0), 1)
        saved = json.loads((self.data / "tasks" / "chain-1.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["fsm"]["state"], "paused")
        self.assertEqual(saved["pause_reason"], PAUSE_REASON_BUDGET)

    def test_can_advance_blocked_when_budget_paused(self):
        from lib.application.orchestration.mediator import apply_budget_decision, can_advance

        apply_budget_decision(str(self.data), None, {})
        task = json.loads((self.data / "tasks" / "chain-1.json").read_text(encoding="utf-8"))
        ok, why = can_advance(str(self.data), task)
        self.assertFalse(ok)
        self.assertIn(why, ("budget_paused", "task_paused"))


class TestLayerOrchImports(unittest.TestCase):
    def test_ports_export(self):
        from lib.ports import BudgetMeterPort, NotifierPort, TaskFsmPort

        self.assertTrue(TaskFsmPort)
        self.assertTrue(BudgetMeterPort)
        self.assertTrue(NotifierPort)


if __name__ == "__main__":
    unittest.main()
