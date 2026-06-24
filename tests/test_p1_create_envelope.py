"""P1 · Envelope-only create · Tier-0 Planner · Legacy 410。"""
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

import lib.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


_utils.file_lock = _noop_file_lock

from lib.api.handlers_tasks import handle_task_create
from lib.tracker import TaskTracker
from lib.utils import json_read


class _FakeHandler:
    def __init__(self, data_dir: str, body: dict):
        self.data_dir = data_dir
        self._body = body
        self.status = 200
        self.payload = None

    def _read_post_body(self):
        return self._body

    def _send_json(self, payload, status=200):
        self.payload = payload
        self.status = status


def _seed_store(tmp: str) -> None:
    root = os.path.join(os.path.dirname(__file__), "..", "store")
    for sub in ("roles/json", "workflows", "dispatch", "rules"):
        src = os.path.join(root, sub)
        dst = os.path.join(tmp, sub)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
    os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "inbox", "dali"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "inbox", "lingxiao"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "msg-files"), exist_ok=True)
    json_write = __import__("lib.utils", fromlist=["json_write"]).json_write
    json_write(os.path.join(tmp, "inbox", "dali", "inbox.json"), {"agent": "dali", "messages": []})
    json_write(os.path.join(tmp, "inbox", "lingxiao", "inbox.json"), {"agent": "lingxiao", "messages": []})
    json_write(os.path.join(tmp, "config.json"), {"mailbus_internal_llm": {"guardrails": {"await_plan_approval_tier_min": "M"}}})


class TestP1CreateEnvelope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_legacy_create_returns_410(self):
        h = _FakeHandler(self.tmp, {
            "task_id": "legacy-test",
            "summary": "x",
            "chain": ["lingzhao"],
        })
        handle_task_create(h)
        self.assertEqual(h.status, 410)
        self.assertEqual(h.payload.get("error"), "legacy_deprecated")

    def test_explicit_envelope_create(self):
        example_path = os.path.join(
            os.path.dirname(__file__), "..", "store", "examples", "a2a-task.example.json",
        )
        with open(example_path, encoding="utf-8") as f:
            body = json.load(f)
        body["task_id"] = "p1-bugfix-test-20260618"
        h = _FakeHandler(self.tmp, body)
        handle_task_create(h)
        self.assertEqual(h.status, 201, h.payload)
        task = h.payload["task"]
        self.assertEqual(task["chain"][0]["role_type"], 8)
        self.assertIn(task["chain"][0]["to_agent"], ("dali", "lingxiao"))
        self.assertEqual(task["chain"][0]["planned_role_types"], [5, 12])
        self.assertEqual(task["fsm"]["state"], "executing")

    def test_auto_mode_bugfix(self):
        h = _FakeHandler(self.tmp, {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "auto-bugfix-20260618",
            "intent": "Fix login 500",
            "initiator": "human",
            "mode": "auto",
            "tier": "S",
            "task_type": "bugfix",
        })
        handle_task_create(h)
        self.assertEqual(h.status, 201, h.payload)
        chain = h.payload["task"]["chain"][0]
        self.assertEqual(chain["planned_role_types"], [5, 12])

    def test_schema_invalid_missing_intent(self):
        h = _FakeHandler(self.tmp, {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "bad-envelope",
            "initiator": "human",
            "mode": "explicit",
            "tier": "S",
            "planned_chain": [{"role_type": 8}],
        })
        handle_task_create(h)
        self.assertEqual(h.status, 400)
        self.assertEqual(h.payload.get("error"), "schema_invalid")

    def test_task_exists_409(self):
        body = {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "dup-task-20260618",
            "intent": "dup",
            "initiator": "human",
            "mode": "explicit",
            "tier": "S",
            "task_type": "bugfix",
            "planned_chain": [{"role_type": 8}, {"role_type": 5}, {"role_type": 12}],
        }
        handle_task_create(_FakeHandler(self.tmp, body))
        h2 = _FakeHandler(self.tmp, body)
        handle_task_create(h2)
        self.assertEqual(h2.status, 409)
        self.assertEqual(h2.payload.get("error"), "task_exists")


if __name__ == "__main__":
    unittest.main()
