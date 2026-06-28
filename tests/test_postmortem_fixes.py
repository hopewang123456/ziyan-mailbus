"""game-courier postmortem 回归：显式链终态、timestamp、phantom inbox、verify、container body。"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, MsgStatus
from lib.pipeline_task import (
    pipeline_inbox_may_mark_done,
    pipeline_repush_cooldown_minutes,
    side_audit_deferred_for_reviewer,
)
from lib.task_fsm import (
    apply_submit,
    ensure_fsm,
    result_applies_to_step,
    result_mtime_ok,
    write_step_result,
    _normalize_result_timestamp,
)
from lib.utils import json_write
from lib.workflow.engine import maybe_block_after_step
from lib.verify.deliverable_check import check_windows_launch_files, run_scripted_interactive
from lib.verify.runner import run_step_verify


def _seed_workflow(tmp: str) -> None:
    wf_dir = os.path.join(tmp, "workflows")
    os.makedirs(wf_dir, exist_ok=True)
    json_write(os.path.join(wf_dir, "registry.json"), {
        "defaults": {"unknown_task_type_workflow": "llm_adaptive"},
        "workflows": {
            "llm_adaptive": {
                "id": "llm_adaptive",
                "mode": "llm_adaptive",
                "llm_policy": {
                    "confirm_gate_id": "llm_step_confirm",
                    "max_llm_routes_per_task": 12,
                },
            },
        },
    })


class TestExplicitChainTerminal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed_workflow(self.tmp)
        json_write(os.path.join(self.tmp, "human-queue.json"), {"items": []})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_llm_adaptive_skipped_when_planned_role_types_exhausted(self):
        task = {
            "task_id": "game-courier-test",
            "status": "running",
            "chain": [
                {
                    "step": 12,
                    "step_id": "s12",
                    "to_person": "yige",
                    "status": "running",
                    "planned_role_types": [],
                }
            ],
            "extensions": {"ziyan": {"workflow": {"workflow_id": "llm_adaptive"}}},
        }
        ensure_fsm(task)
        with patch("lib.workflow.llm_route.route_next_step") as mock_route:
            block = maybe_block_after_step(
                task, task["chain"][-1], {"conclusion": "done"}, data_dir=self.tmp,
            )
        self.assertIsNone(block)
        mock_route.assert_not_called()


class TestStaleTimestamp(unittest.TestCase):
    def test_normalize_raises_stale_timestamp(self):
        step = {"started_at": "2026-06-25T12:00:00+08:00"}
        out = _normalize_result_timestamp(step, "2026-06-25T10:00:00+08:00")
        self.assertNotEqual(out, "2026-06-25T10:00:00+08:00")

    def test_apply_submit_rejects_stale_timestamp(self):
        tmp = tempfile.mkdtemp()
        try:
            task = {
                "task_id": "t-stale",
                "status": "running",
                "chain": [{
                    "step": 1,
                    "step_id": "s1",
                    "to_agent": "dali",
                    "to_person": "dali",
                    "status": "running",
                    "started_at": "2026-06-25T12:00:00+08:00",
                }],
            }
            ensure_fsm(task)
            json_write(os.path.join(tmp, "config.json"), {})
            result = {
                "task_id": "t-stale",
                "agent": "dali",
                "pipeline_step": 1,
                "conclusion": "done",
                "timestamp": "2026-06-25T10:00:00+08:00",
            }
            out = apply_submit(task, result, data_dir=tmp)
            self.assertFalse(out.get("ok"))
            self.assertEqual(out.get("error"), "stale_timestamp")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_write_step_result_clamps_timestamp(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "msg-results", "t1"), exist_ok=True)
            step = {
                "step": 1,
                "step_id": "s1",
                "started_at": "2026-06-25T12:00:00+08:00",
            }
            write_step_result(
                tmp, "t1", step,
                {"agent": "dali", "conclusion": "done", "timestamp": "2026-06-25T08:00:00+08:00"},
                immediate_advance=False,
            )
            path = os.path.join(tmp, "msg-results", "t1", "step-s1.json")
            saved = json.load(open(path, encoding="utf-8"))
            self.assertNotEqual(saved["timestamp"], "2026-06-25T08:00:00+08:00")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestPhantomInbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        tid = "pipe-phantom"
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "dali"), exist_ok=True)
        json_write(os.path.join(self.tmp, "tasks", f"{tid}.json"), {
            "task_id": tid,
            "status": "running",
            "chain": [{"step": 1, "to_agent": "dali", "to_person": "dali", "status": "running"}],
        })
        self.tid = tid

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pipeline_may_not_mark_done_without_result(self):
        entry = {
            "id": "msg-1",
            "type": "task",
            "content": f"【{self.tid}】execute",
            "action": {"execute": True},
        }
        ok, reason = pipeline_inbox_may_mark_done(self.tmp, "dali", entry)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_msg_results")


class TestCooldownAndAuditDefer(unittest.TestCase):
    def test_primary_cooldown_default_six(self):
        cd = pipeline_repush_cooldown_minutes({}, is_primary=True)
        self.assertEqual(cd, 6.0)

    def test_side_audit_deferred_when_primary_running(self):
        tmp = tempfile.mkdtemp()
        try:
            tid = "primary-run"
            os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
            json_write(os.path.join(tmp, "tasks", f"{tid}.json"), {
                "task_id": tid,
                "status": "running",
                "chain": [{"step": 1, "to_agent": "lingjian", "status": "running"}],
            })
            json_write(os.path.join(tmp, "iterations", "iteration-state.json"), {
                "primary_task_id": tid,
            })
            self.assertTrue(side_audit_deferred_for_reviewer(tmp, "lingjian"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestContainerPushBody(unittest.TestCase):
    def test_rewrite_removes_windows_drive(self):
        from lib.utils import rewrite_host_store_refs

        data = r"E:\ai_tools\mail\store"
        text = f"path: {data}\\msg-files\\a.md"
        out = rewrite_host_store_refs(data, text, {"type": "hermes_profile"})
        self.assertNotIn("E:\\", out)
        self.assertIn("/mailbus/store/", out)


class TestVerifyDeliverable(unittest.TestCase):
    def test_windows_launch_missing_files(self):
        tmp = tempfile.mkdtemp()
        try:
            ok, msg = check_windows_launch_files(tmp)
            self.assertFalse(ok)
            self.assertIn("play.ps1", msg)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_scripted_interactive_missing_main(self):
        tmp = tempfile.mkdtemp()
        try:
            ok, msg = run_scripted_interactive(tmp)
            self.assertFalse(ok)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
