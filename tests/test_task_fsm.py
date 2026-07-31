"""task_fsm 状态机单元测试。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.orchestration.task_fsm import (
    TaskFsmState,
    StepFsmState,
    apply_pause,
    apply_rollback,
    apply_submit,
    ensure_fsm,
    fsm_summary,
    get_active_step,
    list_executable_tasks,
    read_step_result,
    result_applies_to_step,
    step_result_path,
    write_step_result,
)
from lib.utils import json_write


def _task(chain, task_id="test-task", status="running"):
    return {
        "task_id": task_id,
        "status": status,
        "chain": chain,
    }


class TestTaskFsm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_ensure_fsm_migrates_legacy_chain(self):
        task = _task([{
            "step": 1,
            "to_role": "方案设计师",
            "to_person": "lingzhao",
            "status": "running",
        }])
        ensure_fsm(task)
        step = task["chain"][0]
        self.assertEqual(step["step_id"], "s1")
        self.assertEqual(step["fsm_state"], StepFsmState.AWAITING_RESULT.value)
        self.assertIn("fsm", task)
        self.assertEqual(task["fsm"]["state"], TaskFsmState.EXECUTING.value)

    def test_stale_prior_step_not_wrong_agent(self):
        chain = [{"step": 5, "step_id": "s5", "to_person": "lingxiao", "to_role": "开发工程师", "status": "running", "fsm_state": "awaiting_result"}]
        result = {"task_id": "t1", "agent": "xiaoqi", "pipeline_step": 4, "conclusion": "done"}
        ok, reason = result_applies_to_step(result, "t1", chain[0], chain)
        self.assertFalse(ok)
        self.assertEqual(reason, "stale_prior_step")

    def test_apply_submit_advances(self):
        task = _task([{
            "step": 1,
            "step_id": "s1",
            "to_role": "方案设计师",
            "to_person": "lingzhao",
            "status": "running",
            "fsm_state": "awaiting_result",
            "planned_agents": ["lingxi"],
        }])
        ensure_fsm(task)
        result = {
            "task_id": "test-task",
            "step_id": "s1",
            "agent": "lingzhao",
            "pipeline_step": 1,
            "conclusion": "done",
            "summary": "ok",
        }
        out = apply_submit(task, result, agents={"lingxi": {}, "lingzhao": {}})
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "advance")
        self.assertEqual(out["next_person"], "lingxi")
        self.assertEqual(len(task["chain"]), 2)

    def test_per_step_result_file(self):
        step = {"step": 2, "step_id": "s2", "to_person": "lingxi"}
        write_step_result(self.tmp, "t1", step, {
            "agent": "lingxi", "pipeline_step": 2, "conclusion": "done",
        })
        p = step_result_path(self.tmp, "t1", "s2")
        self.assertTrue(os.path.isfile(p))
        r = read_step_result(self.tmp, "t1", step)
        self.assertEqual(r["agent"], "lingxi")

    def test_rollback_creates_redo_step(self):
        task = _task([
            {"step": 1, "step_id": "s1", "to_person": "lingzhao", "to_role": "方案设计师", "status": "completed", "fsm_state": "completed"},
            {"step": 2, "step_id": "s2", "to_person": "lingxi", "to_role": "技术研究员", "status": "running", "fsm_state": "awaiting_result"},
        ])
        ensure_fsm(task)
        out = apply_rollback(task, to_step=1, reason="方案不合格")
        self.assertTrue(out["ok"])
        nxt = out["next_step"]
        self.assertEqual(nxt["to_person"], "lingzhao")
        self.assertEqual(nxt["attempt"], 2)
        self.assertIn("rollback_from", nxt)

    def test_pause_v3_style(self):
        task = _task([{"step": 5, "to_person": "lingxiao", "status": "running"}], task_id="game-stellar-v3-20260617")
        ensure_fsm(task)
        apply_pause(task, reason="FSM改造")
        self.assertEqual(task["fsm"]["state"], TaskFsmState.PAUSED.value)
        self.assertEqual(task["status"], "paused")

    def test_priority_sort(self):
        t1 = _task([], task_id="a")
        t1["fsm"] = {"state": "executing", "priority": 30}
        t2 = _task([], task_id="b")
        t2["fsm"] = {"state": "executing", "priority": 10}
        ordered = list_executable_tasks([t1, t2])
        self.assertEqual(ordered[0]["task_id"], "b")

    def test_fsm_summary(self):
        task = _task([{"step": 1, "to_person": "lingzhao", "to_role": "方案设计师", "status": "running"}])
        ensure_fsm(task)
        s = fsm_summary(task)
        self.assertEqual(s["task_id"], "test-task")
        self.assertTrue(s["steps"])


if __name__ == "__main__":
    unittest.main()
