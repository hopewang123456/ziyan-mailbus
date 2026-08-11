"""P3 · intake API · workflows GET · spawn G1。"""
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

from lib.api.handlers_intake import handle_intake_gate_approve, handle_intake_get, handle_intake_list, handle_intake_spawn
from lib.api.handlers_workflows import handle_workflows_list
from lib.application.workflow.intake.gates import on_intake_gate_approve
from lib.application.workflow.intake.store import upsert
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_write


class _FakeHandler:
    def __init__(self, data_dir: str, body: dict = None, *, path: str = "/api/intake"):
        self.data_dir = data_dir
        self._body = body or {}
        self.path = path
        self.status = 200
        self.payload = None

    def _read_post_body(self):
        return self._body

    def _send_json(self, payload, status=200):
        self.payload = payload
        self.status = status


def _seed(tmp: str) -> None:
    from tests.test_helpers import load_pursue_intake_example, seed_runtime_from_sot

    seed_runtime_from_sot(tmp)
    example = load_pursue_intake_example()
    for g in example.get("commercial_gates") or []:
        if g.get("gate_id") == "req_to_lingzhao":
            g["status"] = "pending"
        if g.get("gate_id") in ("customer_design_ok", "start_delivery"):
            g["status"] = "pending"
    example["pipeline_link"] = {}
    json_write(os.path.join(tmp, "leads", "order-intake.json"), [example])


class TestP3Intake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_workflows_list(self):
        h = _FakeHandler(self.tmp, path="/api/workflows")
        handle_workflows_list(h)
        self.assertEqual(h.status, 200)
        self.assertGreaterEqual(len(h.payload.get("workflows", [])), 6)

    def test_intake_get(self):
        h = _FakeHandler(self.tmp, path="/api/intake/intake-20260615-a3f9c2")
        handle_intake_get(h, "intake-20260615-a3f9c2")
        self.assertEqual(h.status, 200)
        self.assertEqual(h.payload["intake"]["intake_id"], "intake-20260615-a3f9c2")

    def test_req_to_lingzhao_spawns_solution_task(self):
        outcome = on_intake_gate_approve(self.tmp, "intake-20260615-a3f9c2", "req_to_lingzhao", {
            "reviewer": "human",
            "brief": "电商小程序需求包",
            "attachments": [{"kind": "file", "ref": "/mailbus/store/leads/req.md", "label": "需求"}],
        })
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertTrue(outcome.get("spawned_task_id", "").startswith("sol-intake-"))
        tr = TaskTracker(self.tmp)
        task = tr.get(outcome["spawned_task_id"])
        self.assertIsNotNone(task)
        self.assertEqual(task["chain"][0]["role_type"], 1)
        self.assertEqual(task["extensions"]["ziyan"]["intake"]["intake_id"], "intake-20260615-a3f9c2")

    def test_low_level_spawn_content(self):
        from lib.application.workflow.intake.store import get
        intake = get(self.tmp, "intake-20260615-a3f9c2")
        for g in intake.get("commercial_gates") or []:
            if g.get("gate_id") == "content_start":
                g["status"] = "approved"
                g["attachments"] = [{"kind": "file", "ref": "/tmp/topic.md", "label": "选题"}]
        upsert(self.tmp, intake)
        h = _FakeHandler(self.tmp, {"kinds": ["content"], "tier": "M"})
        handle_intake_spawn(h, "intake-20260615-a3f9c2")
        self.assertEqual(h.status, 201)
        self.assertTrue(h.payload["spawned"]["content"].startswith("vid-intake-"))
        tr = TaskTracker(self.tmp)
        self.assertIsNotNone(tr.get(h.payload["spawned"]["content"]))


if __name__ == "__main__":
    unittest.main()
