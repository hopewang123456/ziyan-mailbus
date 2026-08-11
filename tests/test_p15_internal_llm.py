"""P1.5 · Internal LLM Tier-1 fallback · stub provider · API。"""
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

from lib.api.handlers_internal_llm import handle_internal_llm_dry_run, handle_internal_llm_status
from lib.api.handlers_tasks import handle_task_create
from lib.application.internal_llm.planner import plan_with_llm
from lib.api.internal_llm_status import llm_status
from lib.adapters.internal_llm.probe import probe_all
from lib.application.orchestration.router.planner import PlanError, plan_replan, plan_task
from lib.infra.utils import json_write


class _FakeHandler:
    def __init__(self, data_dir: str, body: dict = None):
        self.data_dir = data_dir
        self._body = body or {}
        self.status = 200
        self.payload = None

    def _read_post_body(self):
        return self._body

    def _send_json(self, payload, status=200):
        self.payload = payload
        self.status = status


def _seed_store(tmp: str, *, llm_enabled: bool = True) -> None:
    root = os.path.join(os.path.dirname(__file__), "..", "store")
    for sub in ("roles/json", "workflows", "dispatch", "rules", "rag"):
        src = os.path.join(root, sub)
        dst = os.path.join(tmp, sub)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
    os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "inbox", "dali"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "inbox", "lingxiao"), exist_ok=True)
    json_write(os.path.join(tmp, "inbox", "dali", "inbox.json"), {"agent": "dali", "messages": []})
    json_write(os.path.join(tmp, "inbox", "lingxiao", "inbox.json"), {"agent": "lingxiao", "messages": []})
    json_write(os.path.join(tmp, "human-queue.json"), {"version": "1.0.0", "updated_at": "2026-06-18T00:00:00+08:00", "items": []})
    llm_cfg = {
        "enabled": llm_enabled,
        "provider_priority": ["stub"],
        "providers": {"stub": {"kind": "stub"}},
        "rag": {"enabled": True, "max_chunks": 4, "sources": [
            {"id": "role-types", "path": "roles/json/role-types.json", "priority": 90},
        ]},
        "triggers": {"plan_task": True},
        "guardrails": {
            "require_rag_citations": True,
            "await_plan_approval_tier_min": "M",
        },
        "budget": {"max_calls_per_hour": 30, "max_calls_per_task": 5},
    }
    json_write(os.path.join(tmp, "config.json"), {
        "mailbus_internal_llm": llm_cfg,
    })


class TestP15InternalLLM(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tier0_still_used_for_bugfix(self):
        cfg = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))
        out = plan_task({
            "mode": "auto",
            "task_type": "bugfix",
            "tier": "S",
            "intent": "fix login",
        }, data_dir=self.tmp, config=cfg)
        self.assertEqual(out["plan_meta"]["method"], "rules")
        self.assertEqual([x["role_type"] for x in out["planned_chain"]], [8, 5, 12])

    def test_custom_falls_back_to_llm_stub(self):
        cfg = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))
        out = plan_with_llm({
            "task_id": "custom-test",
            "intent": "评估 Redis 做 session 缓存",
            "mode": "auto",
            "tier": "M",
            "task_type": "custom",
        }, data_dir=self.tmp, config=cfg["mailbus_internal_llm"])
        self.assertEqual(out["plan_meta"]["method"], "internal_llm")
        self.assertGreaterEqual(len(out["planned_chain"]), 3)
        self.assertTrue(out.get("rag_citations"))

    def test_create_custom_task_via_api(self):
        h = _FakeHandler(self.tmp, {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "custom-api-20260618",
            "intent": "评估 Redis session 缓存方案",
            "initiator": "human",
            "mode": "auto",
            "tier": "S",
            "task_type": "custom",
        })
        handle_task_create(h)
        self.assertEqual(h.status, 201, h.payload)
        self.assertEqual(h.payload["task"]["plan_meta"]["method"], "internal_llm")

    def test_custom_without_llm_returns_400(self):
        _seed_store(self.tmp, llm_enabled=False)
        h = _FakeHandler(self.tmp, {
            "protocol_version": "mailbus-a2a/1",
            "task_id": "custom-no-llm",
            "intent": "unknown path",
            "initiator": "human",
            "mode": "auto",
            "tier": "S",
            "task_type": "custom",
        })
        handle_task_create(h)
        self.assertEqual(h.status, 400)
        self.assertEqual(h.payload.get("error"), "plan_failed")

    def test_status_api(self):
        h = _FakeHandler(self.tmp)
        handle_internal_llm_status(h)
        self.assertEqual(h.status, 200)
        self.assertTrue(h.payload.get("enabled"))

    def test_dry_run_api(self):
        h = _FakeHandler(self.tmp, {
            "intent": "调研消息队列选型",
            "tier": "M",
            "task_type": "custom",
            "provider": "stub",
        })
        handle_internal_llm_dry_run(h)
        self.assertEqual(h.status, 200, h.payload)
        self.assertIn("planned_chain", h.payload["result"])

    def test_health_includes_rag_and_model_available(self):
        h = _FakeHandler(self.tmp)
        from lib.api.handlers_internal_llm import handle_internal_llm_health

        handle_internal_llm_health(h)
        self.assertEqual(h.status, 200)
        self.assertIn("rag", h.payload)
        self.assertIn("chunks", h.payload["rag"])
        for p in h.payload.get("providers") or []:
            if p.get("kind") == "stub":
                self.assertTrue(p.get("ok"))

    def test_replan_forces_llm_not_tier0(self):
        cfg = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))
        out = plan_replan({
            "mode": "auto",
            "task_type": "bugfix",
            "tier": "S",
            "intent": "fix login",
            "constraints": {"replan_reason": "wrong chain"},
        }, data_dir=self.tmp, config=cfg)
        self.assertEqual(out["plan_meta"]["method"], "internal_llm")

    def test_reject_unknown_agent_in_planner(self):
        cfg = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))["mailbus_internal_llm"]
        cfg = {**cfg, "provider_priority": ["stub"]}
        with unittest.mock.patch(
            "lib.adapters.internal_llm.client._stub_complete",
            return_value=json.dumps({
                "planned_chain": [{"role_type": 8, "reason": "dev", "agent_id": "not-a-real-agent"}],
                "plan_meta": {"method": "internal_llm", "task_type_guess": "custom", "confidence": 0.8},
                "rag_citations": [{"source_id": "role-types", "excerpt": "x"}],
            }),
        ):
            with self.assertRaises(PlanError) as ctx:
                plan_with_llm({
                    "task_id": "bad-agent",
                    "intent": "custom task",
                    "tier": "M",
                    "task_type": "custom",
                }, data_dir=self.tmp, config=cfg)
            self.assertEqual(ctx.exception.code, "schema_invalid")


if __name__ == "__main__":
    unittest.main()
