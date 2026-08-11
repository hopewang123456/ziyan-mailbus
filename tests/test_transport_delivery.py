"""persist_step_transport — task.json chain 审计字段持久化。"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.a2a.delivery import persist_step_transport
from lib.core.a2a.types import DispatchContext
from lib.infra.utils import json_read, json_write


def _task_with_chain(tmp: str, *, task_id: str = "feat-auth-001") -> str:
    path = os.path.join(tmp, "tasks", f"{task_id}.json")
    json_write(
        path,
        {
            "task_id": task_id,
            "chain": [
                {"step_id": "s1", "to_agent": "lingzhao", "role_type": 1},
                {"step_id": "s2", "to_agent": "lingzhao", "role_type": 1},
            ],
        },
    )
    return path


class TestPersistStepTransport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_transport_fields_on_matching_step(self):
        task_path = _task_with_chain(self.tmp)
        ctx = DispatchContext(self.tmp, "feat-auth-001", "s1", "lingzhao", 1)
        attempts = [
            {"channel": "a2a_standard", "attempt": 1, "outcome": "ok", "ts": "2026-06-01T00:00:00+08:00"},
        ]
        persist_step_transport(
            self.tmp,
            ctx,
            transport_used="a2a_standard",
            transport_attempts=attempts,
            a2a_task_id="a2a-task-abc",
        )
        task = json_read(task_path, {})
        step = next(s for s in task["chain"] if s["step_id"] == "s1")
        self.assertEqual(step["transport_used"], "a2a_standard")
        self.assertEqual(step["transport_attempts"], attempts)
        self.assertEqual(step["a2a_task_id"], "a2a-task-abc")
        self.assertNotIn("a2a_retries_exhausted", step)
        self.assertIn("updated_at", task)

    def test_writes_retries_exhausted_flag(self):
        task_path = _task_with_chain(self.tmp)
        ctx = DispatchContext(self.tmp, "feat-auth-001", "s2", "lingzhao", 1)
        attempts = [
            {"channel": "a2a_standard", "attempt": 1, "outcome": "fail", "error": "503"},
            {"channel": "file_bus", "attempt": 1, "outcome": "ok", "fallback_from": "a2a_standard"},
        ]
        persist_step_transport(
            self.tmp,
            ctx,
            transport_used="file_bus",
            transport_attempts=attempts,
            a2a_retries_exhausted=True,
        )
        step = next(s for s in json_read(task_path, {})["chain"] if s["step_id"] == "s2")
        self.assertEqual(step["transport_used"], "file_bus")
        self.assertTrue(step["a2a_retries_exhausted"])
        self.assertEqual(len(step["transport_attempts"]), 2)

    def test_noop_when_task_file_missing(self):
        ctx = DispatchContext(self.tmp, "missing-task", "s1", "lingzhao", 1)
        persist_step_transport(
            self.tmp,
            ctx,
            transport_used="file_bus",
            transport_attempts=[],
        )
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "tasks", "missing-task.json")))

    def test_other_steps_unchanged_when_step_id_not_found(self):
        task_path = _task_with_chain(self.tmp)
        ctx = DispatchContext(self.tmp, "feat-auth-001", "s99", "lingzhao", 1)
        persist_step_transport(
            self.tmp,
            ctx,
            transport_used="a2a_standard",
            transport_attempts=[{"channel": "a2a_standard", "attempt": 1, "outcome": "ok"}],
        )
        task = json_read(task_path, {})
        for step in task["chain"]:
            self.assertNotIn("transport_used", step)


if __name__ == "__main__":
    unittest.main()
