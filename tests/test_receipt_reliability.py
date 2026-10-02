"""M2b 回执可靠性：首派幂等（spawn 后 scan 不二推）+ 超时升级链（TIMEOUT → 待裁决）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_task_timeout_source_pages_owner(self):
        from lib.adapters.orchestration.human_queue import ABNORMAL_QUEUE_SOURCES

        self.assertIn("task_timeout", ABNORMAL_QUEUE_SOURCES)


if __name__ == "__main__":
    unittest.main()
