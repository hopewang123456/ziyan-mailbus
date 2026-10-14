"""FSM / 安全 / pipeline 结果校验回归测试。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.security import safe_report_path
from lib.adapters.ops.archiver import _is_old
from lib.domain.models import Inbox
from lib.application.orchestration.pipeline.result_check import pipeline_step_result_matches
from lib.adapters.orchestration.task_fsm import ensure_fsm, revert_failed_advance, write_step_result
from lib.infra.utils import json_write


class TestSafeReportPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "reports"))
        with open(os.path.join(self.tmp, "reports", "ok.md"), "w") as f:
            f.write("# ok")

    def test_rejects_traversal(self):
        self.assertIsNone(safe_report_path(self.tmp, "reports", "../config.json"))
        self.assertIsNone(safe_report_path(self.tmp, "reports", "..\\ok.md"))

    def test_accepts_valid(self):
        p = safe_report_path(self.tmp, "reports", "ok.md")
        self.assertTrue(p and p.endswith("ok.md"))


class TestPipelineResultCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "tasks"))
        os.makedirs(os.path.join(self.tmp, "msg-results", "t1"))

    def test_per_step_result_matches(self):
        task = {
            "task_id": "t1",
            "status": "running",
            "chain": [{
                "step": 2, "step_id": "s2", "to_person": "agent-g",
                "to_role": "开发工程师", "status": "running",
                "fsm_state": "awaiting_result", "result_consumed": True,
            }],
        }
        ensure_fsm(task)
        write_step_result(self.tmp, "t1", task["chain"][0], {
            "agent": "agent-g", "pipeline_step": 2, "step_id": "s2",
            "conclusion": "done", "summary": "ok",
        })
        json_write(os.path.join(self.tmp, "tasks", "t1.json"), task)
        ok, reason = pipeline_step_result_matches(
            self.tmp, task, "agent-g", require_consumed=True,
        )
        self.assertTrue(ok, reason)

    def test_stale_legacy_does_not_match(self):
        task = {
            "task_id": "t1",
            "status": "running",
            "chain": [{
                "step": 2, "step_id": "s2", "to_person": "agent-g",
                "status": "running", "fsm_state": "awaiting_result",
            }],
        }
        ensure_fsm(task)
        json_write(os.path.join(self.tmp, "msg-results", "t1.json"), {
            "agent": "agent-m", "pipeline_step": 1, "conclusion": "done",
        })
        ok, reason = pipeline_step_result_matches(self.tmp, task, "agent-g")
        self.assertFalse(ok)
        # legacy flat msg-results/{tid}.json 已移除；无 step 路径时为 missing
        self.assertIn(reason, ("stale_prior_step", "missing_msg_results", "stale"))


class TestArchiverDoneAt(unittest.TestCase):
    def test_is_old_uses_done_at_fallback(self):
        inbox = Inbox(agent="test")
        msg = {"id": "m1", "done_at": "2020-01-01T00:00:00+08:00"}
        self.assertTrue(_is_old(inbox, msg, archive_days=1))


class TestRevertFailedAdvance(unittest.TestCase):
    def test_reverts_chain_and_step(self):
        task = {
            "task_id": "t1",
            "status": "running",
            "chain": [
                {"step_id": "s1", "to_person": "a", "status": "completed",
                 "fsm_state": "completed", "completed_at": "x", "report": {}},
                {"step_id": "s2", "to_person": "b", "status": "running"},
            ],
        }
        ensure_fsm(task)
        completed = task["chain"][0]
        nxt = task["chain"][1]
        revert_failed_advance(task, completed, nxt)
        self.assertEqual(len(task["chain"]), 1)
        self.assertEqual(completed["fsm_state"], "awaiting_result")
        self.assertNotIn("completed_at", completed)
        self.assertEqual(task["fsm"]["active_step_id"], "s1")
        self.assertEqual(task["assignee"], "a")


class TestReminderCleanup(unittest.TestCase):
    def test_is_remind_message(self):
        from lib.application.ops.reminder_cleanup import _is_remind_message
        self.assertTrue(_is_remind_message("tracker-remind-1", ""))
        self.assertTrue(_is_remind_message("remind-1-x", ""))
        self.assertFalse(_is_remind_message("msg-abc", "普通通知"))

    def test_task_is_stale(self):
        from lib.application.ops.reminder_cleanup import _task_is_stale_for_remind
        self.assertTrue(_task_is_stale_for_remind(None))
        self.assertTrue(_task_is_stale_for_remind({"status": "success"}))
        self.assertTrue(_task_is_stale_for_remind({"status": "running", "fsm": {"state": "paused"}}))
        self.assertFalse(_task_is_stale_for_remind({"status": "running", "fsm": {"state": "executing"}}))

    def test_extract_task_refs(self):
        from lib.application.ops.reminder_cleanup import _extract_task_refs
        refs = _extract_task_refs(
            {"task_id": "t1", "id": "tracker-remind-1"},
            "任务「摘要」【game-v3】",
        )
        self.assertIn("t1", refs)
        self.assertIn("game-v3", refs)


if __name__ == "__main__":
    unittest.main()
