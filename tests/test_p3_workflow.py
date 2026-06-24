"""P3 · Workflow engine · gates API · llm_adaptive block。"""
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

from lib.api.handlers_gates import handle_gate_approve
from lib.api.handlers_tasks import handle_task_create
from lib.task_fsm import apply_submit, ensure_fsm
from lib.utils import json_write
from lib.workflow.engine import bind_workflow, maybe_block_after_step, on_gate_approve


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


def _seed(tmp: str) -> None:
    root = os.path.join(os.path.dirname(__file__), "..", "store")
    for sub in ("roles/json", "workflows", "dispatch", "rules", "rag"):
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
        "mailbus_internal_llm": {
            "enabled": True,
            "provider_priority": ["stub"],
            "providers": {"stub": {"kind": "stub"}},
            "triggers": {"plan_task": True},
            "guardrails": {"require_rag_citations": True, "await_plan_approval_tier_min": "L"},
            "budget": {"max_calls_per_hour": 30, "max_calls_per_task": 5},
        },
    })


def _finance_task(tmp: str) -> dict:
    from lib.dispatch.role_resolver import resolve_agent_for_role_type
    from lib.pipeline_chain import init_chain_from_planned

    tid = "fin-gate-test-20260618"
    chain = init_chain_from_planned(
        [{"role_type": 10}],
        tid,
        resolve_agent=lambda rt, pin: resolve_agent_for_role_type(tmp, rt, pin_agent=pin),
    )
    task = {
        "task_id": tid,
        "protocol_version": "mailbus-a2a/1",
        "intent": "商后回款跟进验收",
        "task_type": "finance",
        "tier": "S",
        "status": "running",
        "chain": chain,
        "extensions": {},
        "created_at": "2026-06-18T00:00:00+08:00",
    }
    ensure_fsm(task)
    task["fsm"]["state"] = "executing"
    bind_workflow(task, {"task_type": "finance", "extensions": {}}, data_dir=tmp)
    task["extensions"]["ziyan"]["workflow"]["phase"] = "setup"
    json_write(os.path.join(tmp, "tasks", f"{tid}.json"), task)
    return task


class TestP3Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_binds_workflow(self):
        h = _FakeHandler(self.tmp, {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "wf-bind-bugfix",
            "intent": "fix bug",
            "initiator": "human",
            "mode": "auto",
            "tier": "S",
            "task_type": "bugfix",
        })
        handle_task_create(h)
        self.assertEqual(h.status, 201, h.payload)
        wf = h.payload["task"]["extensions"]["ziyan"]["workflow"]
        self.assertEqual(wf["workflow_id"], "bugfix_s")

    def test_step_done_blocks_finance_gate(self):
        task = _finance_task(self.tmp)
        step = task["chain"][-1]
        step["fsm_state"] = "awaiting_result"
        result = {
            "task_id": task["task_id"],
            "agent": step.get("to_agent"),
            "pipeline_step": 1,
            "conclusion": "done",
            "summary": "账期已写入 accounts.json",
        }
        out = apply_submit(task, result, data_dir=self.tmp)
        self.assertEqual(out.get("action"), "blocked")
        self.assertEqual(task["fsm"].get("gate_id"), "remind_approve")
        self.assertEqual(task["fsm"].get("substate"), "await_gate")

    def test_gate_approve_append_remind_phase(self):
        task = _finance_task(self.tmp)
        task["fsm"]["state"] = "blocked"
        task["fsm"]["substate"] = "await_gate"
        task["fsm"]["gate_id"] = "remind_approve"
        task["chain"][-1]["fsm_state"] = "completed"
        task["chain"][-1]["status"] = "completed"

        outcome = on_gate_approve(self.tmp, task, "remind_approve", {
            "reviewer": "human",
            "comment": "批准提醒",
            "attachments": [],
        })
        self.assertTrue(outcome.get("ok"), outcome)
        inst = next(g for g in task["extensions"]["ziyan"]["workflow"]["gates"] if g["gate_id"] == "remind_approve")
        self.assertEqual(inst["status"], "approved")
        self.assertEqual(task["fsm"]["state"], "executing")
        self.assertEqual(task["extensions"]["ziyan"]["workflow"].get("phase"), "remind")
        self.assertGreaterEqual(len(task["chain"]), 1)


if __name__ == "__main__":
    unittest.main()
