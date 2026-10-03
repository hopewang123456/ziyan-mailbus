"""M2b 回执可靠性：首派幂等（spawn 后 scan 不二推）+ 超时升级链（TIMEOUT → 待裁决）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.a2a.file_bus import FileBusTransport
from lib.core.a2a.types import DispatchContext
from tests.test_helpers import seed_a2a_harness


class _SpawnOnlyHarness:
    def __init__(self):
        self.spawned: list[dict] = []

    def spawn(self, agent_id: str, payload: dict):
        self.spawned.append({"agent_id": agent_id, **payload})
        return mock.Mock()

    def wait_completion(self, session, timeout: int = 300):
        raise AssertionError("wait_on_dispatch off — must not wait")


class TestDispatchIdempotency(unittest.TestCase):
    """首派 spawn 后 inbox 消息应为 pushed（scan 二次推送被 P2 串行约束挡住）。"""

    def _ctx(self, tmp: str) -> DispatchContext:
        return DispatchContext(
            tmp, "task-idem-001", "s1", "agent-c", 8,
            intent="【task-idem-001】do the thing",
        )

    def _agents(self):
        return {"agent-c": {"type": "claude_code"}}

    def test_spawn_marks_inbox_pushed(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed_a2a_harness(tmp, mode="production")
            transport = FileBusTransport(harness=_SpawnOnlyHarness(), mode="production")
            r = transport.dispatch(self._ctx(tmp), self._agents())
            self.assertTrue(r.ok)
            inbox = json.load(open(
                os.path.join(tmp, "inbox", "agent-c", "inbox.json"), encoding="utf-8"))
            msgs = [m for m in inbox["messages"] if m.get("task_id") == "task-idem-001"]
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["state"], "pushed")
            self.assertEqual(msgs[0]["pushed_via"], "file_bus_dispatch")

    def test_spawn_failure_leaves_pending_for_scan(self):
        class _BoomHarness:
            def spawn(self, agent_id, payload):
                raise RuntimeError("cli missing")

        with tempfile.TemporaryDirectory() as tmp:
            seed_a2a_harness(tmp, mode="production")
            transport = FileBusTransport(harness=_BoomHarness(), mode="production")
            with self.assertRaises(RuntimeError):
                transport.dispatch(self._ctx(tmp), self._agents())
            inbox = json.load(open(
                os.path.join(tmp, "inbox", "agent-c", "inbox.json"), encoding="utf-8"))
            msgs = [m for m in inbox["messages"] if m.get("task_id") == "task-idem-001"]
            self.assertEqual(msgs[0]["state"], "pending")  # scan 是兜底推送方

    def test_no_harness_leaves_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed_a2a_harness(tmp, mode="production")
            transport = FileBusTransport(harness=None, mode="production")
            r = transport.dispatch(self._ctx(tmp), self._agents())
            self.assertTrue(r.ok)
            inbox = json.load(open(
                os.path.join(tmp, "inbox", "agent-c", "inbox.json"), encoding="utf-8"))
            msgs = [m for m in inbox["messages"] if m.get("task_id") == "task-idem-001"]
            self.assertEqual(msgs[0]["state"], "pending")  # 无 spawn → scan 负责


class TestTimeoutEscalation(unittest.TestCase):
    """check_reminders 超限 TIMEOUT 后必须进待裁决（source=task_timeout）。"""

    def test_timeout_enqueues_human_queue(self):
        from lib.application.orchestration.tracker import TaskTracker
        from lib.infra.utils import json_write
        from datetime import timedelta
        from lib.infra.clock import now_dt

        with tempfile.TemporaryDirectory() as td:
            t = TaskTracker(td)
            t.create("task-esc-001", assignee="agent-c")
            t.update_status("task-esc-001", "running")
            task = t.get("task-esc-001")
            task["chain"] = []  # 摘掉 create() 挂的 pipeline chain（见 test_tracker.py 先例）
            task["updated_at"] = (now_dt() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
            json_write(t._task_path("task-esc-001"), task)
            for _ in range(12):
                t.increment_reminder("task-esc-001")

            escalated = t.check_reminders({"agent-c": {"name": "agent-c"}}, reminder_minutes=0)
            self.assertEqual(t.get("task-esc-001")["status"], "timeout")

            hq = json.load(open(os.path.join(td, "human-queue.json"), encoding="utf-8"))
            entries = [i for i in hq.get("items", []) if i.get("source") == "task_timeout"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["task_id"], "task-esc-001")

class TestTaskTimeoutSourcePagesOwner(unittest.TestCase):
    def test_task_timeout_source_pages_owner(self):
        from lib.adapters.orchestration.human_queue import ABNORMAL_QUEUE_SOURCES

        self.assertIn("task_timeout", ABNORMAL_QUEUE_SOURCES)


class TestPlannedResumeAndReminderGuard(unittest.TestCase):
    """第二产线实锤的两个恢复链 bug 回归。"""

    def test_resume_planned_advance_after_consumed(self):
        """s1 completed+result_consumed、planned 残余、executing → trigger 应补出 s2。"""
        import tempfile as _tempfile

        from lib.application.orchestration.pipeline.trigger import trigger_task
        from lib.application.orchestration.tracker import TaskTracker
        from lib.infra.utils import json_write

        with _tempfile.TemporaryDirectory() as td:
            # 种工位（须带 role_type，否则规划校验/解析拒）
            with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as fh:
                json.dump({"stations": {
                    "developer": {"title": "开发工程师", "role_type": 8,
                                  "candidates": ["agent-b"], "vacancy_policy": "queue"},
                }}, fh)
            t = TaskTracker(td)
            t.create("task-resume-001", assignee="agent-a")
            t.update_status("task-resume-001", "running")
            task = t.get("task-resume-001")
            chain = task.get("chain") or []
            self.assertTrue(chain)
            # 复刻产线现场：s1 completed+consumed，链头挂 planned 残余，fsm=executing
            chain[0].update({
                "to_agent": "agent-a", "to_person": "agent-a",
                "status": "completed", "fsm_state": "completed",
                "result_consumed": True,
                "planned_role_types": [8],
                "planned_stations": ["developer"],
            })
            task["fsm"]["state"] = "executing"
            task["fsm"]["active_step_id"] = chain[0]["step_id"]
            json_write(t._task_path("task-resume-001"), task)

            # agents 里放一个可用候选；patch 工位解析走 role_type 直派
            agents = {"agent-a": {"type": "hermes"}, "agent-b": {"type": "hermes"}}
            with patch("lib.application.orchestration.pipeline.trigger._send_task", return_value=True) as ms:
                r = trigger_task(
                    td, "task-resume-001", agents,
                    {"tasks": td, "inbox": os.path.join(td, "inbox")},
                )
            self.assertTrue(r.get("ok"), r)
            self.assertEqual(r.get("action"), "resume_advance")
            after = t.get("task-resume-001")
            self.assertEqual(len(after["chain"]), 2)
            self.assertEqual(after["chain"][1]["fsm_state"], "dispatched")
            ms.assert_called_once()

    def test_blocked_task_not_reminded(self):
        """blocked（等 owner/裁决）任务不催办、不 timeout（第二产线空催 12 次实锤）。"""
        from lib.application.orchestration.tracker import TaskTracker
        from lib.infra.utils import json_write
        from datetime import timedelta
        from lib.infra.clock import now_dt

        with tempfile.TemporaryDirectory() as td:
            t = TaskTracker(td)
            t.create("task-block-001", assignee="agent-a")
            t.update_status("task-block-001", "running")
            task = t.get("task-block-001")
            task["chain"] = []
            task["updated_at"] = (now_dt() - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%S")
            json_write(t._task_path("task-block-001"), task)
            # 现场是 fsm.blocked + status blocked（owner_confirmation 等裁决门）
            t.update_status("task-block-001", "blocked")

            escalated = t.check_reminders({"agent-a": {"name": "agent-a"}}, reminder_minutes=0)
            self.assertEqual(escalated, [])
            # 也不该被标 timeout
            self.assertEqual(t.get("task-block-001")["status"], "blocked")


class TestFlatDeliveryTolerance(unittest.TestCase):
    """G10/yige 实锤回归：平铺交付路径 + status=done 无 conclusion 的回执必须被消化。"""

    def test_result_paths_include_flat_contract(self):
        from lib.infra.pipeline_results import result_paths_to_try

        paths = result_paths_to_try("/tmp/x", "task-t", {"step_id": "s1"})
        self.assertTrue(any(p.endswith(os.path.join("msg-results", "msg-task-t-s1.json")) for p in paths))

    def test_status_done_without_conclusion_applies(self):
        from lib.adapters.orchestration.task_fsm import result_applies_to_step

        ok, reason = result_applies_to_step(
            {"agent": "yige", "status": "done", "summary": "wrote docs"},
            "task-t",
            {"step_id": "s1", "to_agent": "yige"},
            [],
        )
        self.assertTrue(ok, reason)

    def test_read_step_result_finds_flat_delivery(self):
        """读端回归：read_step_result 必须能取到平铺契约回执（G10 病灶本尊）。

        不走 trigger 全链（fsm 会在单步任务上尝试派发下一步，测试环境必失败
        且与本案无关）——G10 的真实推进由容器 scan 实证。
        """
        import tempfile as _tempfile

        from lib.adapters.orchestration.task_fsm import read_step_result

        with _tempfile.TemporaryDirectory() as td:
            flat = os.path.join(td, "msg-results", "msg-task-flat-001-s1.json")
            os.makedirs(os.path.dirname(flat), exist_ok=True)
            with open(flat, "w", encoding="utf-8") as fh:
                json.dump({"agent": "agent-a", "msg_id": "msg-task-flat-001-s1",
                           "status": "done", "summary": "flat delivery"}, fh)
            r = read_step_result(td, "task-flat-001", {"step_id": "s1"})
            self.assertIsNotNone(r, "平铺回执必须可读")
            self.assertEqual(r.get("status"), "done")


if __name__ == "__main__":
    unittest.main()
