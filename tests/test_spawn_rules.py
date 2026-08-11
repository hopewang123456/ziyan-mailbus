"""P3 · spawn_rules R0–R4。"""
import contextlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("fcntl", MagicMock())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.infra.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


_utils.file_lock = _noop_file_lock

from lib.application.workflow.intake.spawn_rules import (
    bridge_reconcile,
    evaluate,
    load_bridge_config,
    rule_r1_spawn_analyze,
    rule_r2_no_auto_solution,
    rule_r3_spawn_solution,
    rule_r4_spawn_content,
)
from lib.application.workflow.intake.store import upsert
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_write


def _seed(tmp: str) -> None:
    from tests.test_helpers import load_pursue_intake_example, seed_runtime_from_sot

    seed_runtime_from_sot(tmp)
    intake = load_pursue_intake_example()
    intake["decision"] = "pending"
    intake["pipeline_link"] = {}
    json_write(os.path.join(tmp, "leads", "order-intake.json"), [intake])


class TestSpawnRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)
        self.intake_id = "intake-20260615-a3f9c2"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _intake(self):
        from lib.application.workflow.intake.store import get
        return get(self.tmp, self.intake_id)

    def test_r1_eligible_without_analyze_task(self):
        cfg = load_bridge_config(self.tmp)
        m = rule_r1_spawn_analyze(self._intake(), cfg)
        self.assertTrue(m.eligible)
        self.assertEqual(m.rule, "R1")

    def test_r2_blocks_auto_solution_after_pursue(self):
        intake = self._intake()
        intake["decision"] = "pursue"
        intake["pipeline_link"] = {"intake_task_id": f"{self.intake_id}-analyze"}
        upsert(self.tmp, intake)
        tr = TaskTracker(self.tmp)
        tr.create_from_envelope({
            "task_id": f"{self.intake_id}-analyze",
            "intent": "test",
            "initiator": "mailbus",
            "mode": "explicit",
            "tier": "S",
            "task_type": "intake",
            "planned_chain": [{"role_type": 4}],
        }, planned_chain=[{"role_type": 4}], plan_meta={})
        task = tr.get(f"{self.intake_id}-analyze")
        task["status"] = "done"
        json_write(tr._task_path(task["task_id"]), task)
        m = rule_r2_no_auto_solution(intake, self.tmp)
        self.assertTrue(m.eligible)
        self.assertEqual(m.action, "block_auto_solution")

    def test_r3_r4_auto_disabled_by_default(self):
        cfg = load_bridge_config(self.tmp)
        intake = self._intake()
        for g in intake.get("commercial_gates") or []:
            if g.get("gate_id") == "req_to_lingzhao":
                g["status"] = "approved"
            if g.get("gate_id") == "content_start":
                g["status"] = "approved"
        m3 = rule_r3_spawn_solution(intake, cfg)
        m4 = rule_r4_spawn_content(intake, cfg)
        self.assertFalse(m3.eligible)
        self.assertFalse(m4.eligible)

    def test_bridge_reconcile_spawns_analyze(self):
        out = bridge_reconcile(self.tmp)
        self.assertEqual(out["status"], "ok")
        spawned = [r for r in out["results"] if r.get("rule") == "R1" and "task_id" in r]
        self.assertEqual(len(spawned), 1)
        tr = TaskTracker(self.tmp)
        self.assertIsNotNone(tr.get(spawned[0]["task_id"]))

    def test_evaluate_returns_all_rules(self):
        cfg = load_bridge_config(self.tmp)
        matches = evaluate(self._intake(), cfg, data_dir=self.tmp)
        rules = {m.rule for m in matches}
        self.assertEqual(rules, {"R0", "R1", "R2", "R3", "R4"})


if __name__ == "__main__":
    unittest.main()
