"""Phase 6 — decomposition / clarifications 门禁测试。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.decomposition import (
    handle_design_step_decomposition,
    task_requires_decomposition,
    topological_subtask_order,
    validate_subtasks,
)
from lib.human_queue import load_queue
from lib.human_queue_resolve import resolve_human_queue_item
from lib.adapters.orchestration.task_fsm import TaskFsmState, apply_submit
from lib.tracker import TaskTracker
from lib.utils import json_write


def _design_task(**overrides):
    task = {
        "task_id": "decomp-test",
        "protocol_version": "mailbus-a2a/1",
        "tier": "L",
        "intent": "跨模块重构",
        "chain": [{
            "step_id": "s1",
            "step": 1,
            "role_type": 1,
            "to_agent": "lingzhao",
            "to_person": "lingzhao",
            "status": "running",
            "fsm_state": "awaiting_result",
            "planned_role_types": [8, 8, 5],
        }],
        "fsm": {"state": "executing", "active_step_id": "s1"},
    }
    task.update(overrides)
    return task


def _result(**extra):
    base = {
        "task_id": "decomp-test",
        "step_id": "s1",
        "agent": "lingzhao",
        "role_type": 1,
        "pipeline_step": 1,
    }
    base.update(extra)
    return base


class TestDecomposition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "msg-results", "decomp-test"), exist_ok=True)
        json_write(os.path.join(self.tmp, "config.json"), {})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clarifications_blocks_fsm(self):
        task = _design_task()
        out = apply_submit(task, _result(
            conclusion="clarifications_needed",
            decomposition={
                "status": "clarifications_needed",
                "clarifications_needed": [{"question": "用哪个支付渠道？", "blocking": True}],
            },
        ), data_dir=self.tmp)
        self.assertEqual(out["action"], "blocked")
        self.assertEqual(task["fsm"]["state"], TaskFsmState.BLOCKED.value)
        self.assertEqual(task["fsm"]["substate"], "await_owner_confirmation")
        hq = load_queue(self.tmp)
        self.assertTrue(any(i.get("type") == "owner_confirmation" for i in hq["items"]))

    def test_subtasks_applied_to_planned_chain(self):
        task = _design_task()
        step = task["chain"][0]
        subtasks = [
            {"id": "a", "title": "API", "role_type": 8, "depends_on": []},
            {"id": "b", "title": "UI", "role_type": 8, "depends_on": ["a"]},
            {"id": "c", "title": "Review", "role_type": 5, "depends_on": ["b"]},
        ]
        result = _result(
            conclusion="done",
            decomposition={"status": "ready", "subtasks": subtasks},
        )
        dec = handle_design_step_decomposition(task, step, result, data_dir=self.tmp)
        self.assertEqual(dec["action"], "subtasks_applied")
        self.assertEqual(task["chain"][0]["planned_role_types"], [8, 8, 5])

    def test_topo_order(self):
        subtasks = [
            {"id": "b", "title": "B", "role_type": 8, "depends_on": ["a"]},
            {"id": "a", "title": "A", "role_type": 8, "depends_on": []},
        ]
        ordered = topological_subtask_order(subtasks)
        self.assertEqual([x["id"] for x in ordered], ["a", "b"])

    def test_missing_decomposition_on_complex(self):
        task = _design_task()
        self.assertTrue(task_requires_decomposition(task, {"require_for_tiers": ["L", "S"], "coding_role_types": [8], "min_planned_steps_for_complex": 3}))
        step = task["chain"][0]
        result = _result(conclusion="done", summary="done without subtasks")
        dec = handle_design_step_decomposition(task, step, result, data_dir=self.tmp)
        self.assertEqual(dec["action"], "missing_decomposition")

    def test_owner_confirmation_resolve_resume(self):
        task = _design_task()
        json_write(os.path.join(self.tmp, "tasks", "decomp-test.json"), task)
        apply_submit(task, _result(
            conclusion="return_to_owner",
            decomposition={"clarifications_needed": [{"question": "x?"}]},
        ), data_dir=self.tmp)
        json_write(os.path.join(self.tmp, "tasks", "decomp-test.json"), task)
        hq = load_queue(self.tmp)
        item = next(i for i in hq["items"] if i.get("type") == "owner_confirmation")
        _, side = resolve_human_queue_item(self.tmp, item["id"], {"decision": "approved", "comment": "用微信"})
        self.assertTrue(side.get("ok"))
        task2 = TaskTracker(self.tmp).get("decomp-test")
        self.assertEqual(task2["fsm"]["state"], TaskFsmState.EXECUTING.value)

    def test_validate_subtasks_bad_dep(self):
        ok, errs = validate_subtasks([{"id": "x", "title": "t", "role_type": 8, "depends_on": ["missing"]}])
        self.assertFalse(ok)
        self.assertTrue(any("bad_dep" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
