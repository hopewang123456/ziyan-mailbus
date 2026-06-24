"""P1+ · human-queue · approve-plan · accepting 流转。"""
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

from lib.api.handlers_tasks import handle_human_queue, handle_task_create, handle_task_fsm_action
from lib.human_queue import load_queue, list_items
from lib.tracker import TaskTracker
from lib.utils import json_write


class _FakeHandler:
    def __init__(self, data_dir: str, body: dict = None, *, path: str = "/api/human-queue"):
        self.data_dir = data_dir
        self._body = body or {}
        self.path = path
        self.command = "POST"
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
    for d in ("tasks", "inbox/dali", "inbox/lingxiao", "msg-files"):
        os.makedirs(os.path.join(tmp, d), exist_ok=True)
    json_write(os.path.join(tmp, "inbox", "dali", "inbox.json"), {"agent": "dali", "messages": []})
    json_write(os.path.join(tmp, "inbox", "lingxiao", "inbox.json"), {"agent": "lingxiao", "messages": []})
    json_write(os.path.join(tmp, "human-queue.json"), {"version": "1.0.0", "updated_at": "2026-06-18T00:00:00+08:00", "items": []})
    json_write(os.path.join(tmp, "config.json"), {
        "mailbus_internal_llm": {"guardrails": {"await_plan_approval_tier_min": "M"}},
    })


class TestHumanQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_m_tier_enqueues_plan_approval(self):
        body = {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "plan-approval-20260618",
            "intent": "M tier needs approval",
            "initiator": "human",
            "mode": "auto",
            "tier": "M",
            "task_type": "bugfix",
        }
        h = _FakeHandler(self.tmp, body)
        handle_task_create(h)
        self.assertEqual(h.status, 201, h.payload)
        task = h.payload["task"]
        self.assertEqual(task["fsm"]["state"], "created")
        self.assertEqual(task["fsm"]["substate"], "await_plan_approval")
        self.assertIn("human_queue_id", h.payload)

        items, meta = list_items(self.tmp, status="pending", qtype="plan_approval")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["task_id"], "plan-approval-20260618")

    def test_approve_plan_starts_executing(self):
        body = {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "approve-me-20260618",
            "intent": "Approve then execute",
            "initiator": "human",
            "mode": "explicit",
            "tier": "L",
            "task_type": "bugfix",
            "planned_chain": [{"role_type": 8}, {"role_type": 5}],
        }
        handle_task_create(_FakeHandler(self.tmp, body))
        h = _FakeHandler(self.tmp, {"decision": "approved", "reviewer": "human"})
        handle_task_fsm_action(h, "approve-me-20260618", "approve-plan")
        self.assertEqual(h.status, 200, h.payload)
        self.assertEqual(h.payload["fsm"]["fsm_state"], "executing")

        doc = load_queue(self.tmp)
        closed = [i for i in doc["items"] if i["type"] == "plan_approval"]
        self.assertEqual(closed[0]["status"], "approved")

    def test_human_queue_api(self):
        body = {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "hq-api-20260618",
            "intent": "list me",
            "initiator": "human",
            "mode": "auto",
            "tier": "M",
            "task_type": "doc",
        }
        handle_task_create(_FakeHandler(self.tmp, body))
        h = _FakeHandler(self.tmp, path="/api/human-queue?status=pending&type=plan_approval")
        h.command = "GET"
        handle_human_queue(h)
        self.assertEqual(h.status, 200)
        self.assertGreaterEqual(h.payload["total"], 1)


if __name__ == "__main__":
    unittest.main()
