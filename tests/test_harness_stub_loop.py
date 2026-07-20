"""Harness stub + step-result closed-loop 烟雾测试。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.harness import get_harness
from lib.pipeline_results import step_result_path
from lib.pipeline_trigger import trigger
from lib.task_fsm import StepFsmState
from lib.tracker import TaskTracker
from lib.transport.a2a_standard import A2ATransport
from lib.transport.dispatch_integration import build_router
from lib.transport.file_bus import FileBusTransport
from lib.transport.router import TransportRouter
from lib.transport.stub_a2a import StubA2AClient
from lib.transport.types import DispatchContext
from lib.transport.step_result_io import read_step_result_file
from lib.utils import _now_iso, json_read, json_write
from tests.test_helpers import seed_a2a_harness
from unittest.mock import patch


def _lingzhao_agent() -> dict:
    return {
        "type": "hermes_profile",
        "channels": {"a2a": {"enabled": True}, "file_bus": {"enabled": True}},
        "endpoint": {"base_url": "https://mailbus.example/api/a2a/rpc/lingzhao"},
        "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
    }


def _dali_agent() -> dict:
    return {
        "type": "opencode",
        "channels": {"a2a": {"enabled": False}, "file_bus": {"enabled": True}},
    }


def _seed_feat_auth_task(tmp: str, *, started_at: str | None = None) -> None:
    ts = started_at or _now_iso()
    json_write(
        os.path.join(tmp, "tasks", "feat-auth-001.json"),
        {
            "task_id": "feat-auth-001",
            "title": "用户认证模块",
            "status": "running",
            "tier": "M",
            "requires_audit": False,
            "fsm": {"state": "executing", "active_step_id": "s1"},
            "chain": [{
                "step_id": "s1",
                "step": 1,
                "role_type": 1,
                "to_agent": "lingzhao",
                "to_person": "lingzhao",
                "to_role": "方案设计师",
                "status": "running",
                "fsm_state": "awaiting_result",
                "started_at": ts,
                "planned_role_types": [1, 8],
                "result_consumed": False,
            }],
        },
    )


class TestHarnessStubLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(
            self.tmp,
            extra_config={
                "transport": {
                    "use_router": True,
                    "a2a": {"retry_backoff_sec": [0, 0, 0]},
                },
            },
        )
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        agents = cfg.setdefault("agents", {})
        agents["lingzhao"] = _lingzhao_agent()
        agents["dali"] = _dali_agent()
        cfg["harness"] = {
            "mode": "stub",
            "stub_fixtures_dir": "tests/fixtures/harness_stub",
        }
        json_write(cfg_path, cfg)
        self.paths = {"inbox": os.path.join(self.tmp, "inbox")}
        _seed_feat_auth_task(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _agents(self) -> dict:
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            return json.load(f)["agents"]

    def _refresh_result_timestamp(self, step_id: str) -> None:
        path = step_result_path(self.tmp, "feat-auth-001", step_id)
        data = json_read(path, {})
        data["timestamp"] = _now_iso()
        json_write(path, data)

    def _advance_without_redispatch(self, agents: dict) -> None:
        with patch(
            "lib.transport.dispatch_integration.dispatch_pipeline_step",
            return_value={"ok": True, "transport_used": "file_bus"},
        ):
            trigger(self.tmp, agents, self.paths)

    def test_stub_harness_loads_fixture(self):
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        harness = get_harness(cfg)
        session = harness.spawn("dali", {})
        outcome = harness.wait_completion(session)
        self.assertTrue(outcome.ok)
        self.assertIsNotNone(outcome.step_result)

    def test_file_bus_stub_writes_step_result(self):
        transport = FileBusTransport(mode="stub")
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s3", "dali", 8,
            stub_fixture="path-d-dali-opencode.json",
        )
        result = transport.dispatch(ctx, {})
        self.assertTrue(result.ok)
        sr = read_step_result_file(self.tmp, "feat-auth-001", "s3")
        self.assertEqual(sr.get("agent"), "dali")
        self.assertEqual(sr.get("conclusion"), "done")

    def test_h02_feat_auth_three_step_fsm(self):
        """H-02：s1→s2→s3 stub 闭环，三步完成后 task 进入终态。"""
        agents = self._agents()
        router = build_router(self.tmp)
        router.a2a = A2ATransport(rpc=StubA2AClient.from_name("path-a-lingzhao-s1.json"))

        s1 = DispatchContext(
            self.tmp, "feat-auth-001", "s1", "lingzhao", 1,
            stub_fixture="path-a-lingzhao-s1.json",
        )
        self.assertTrue(router.dispatch_step(s1, agents).ok)
        self._refresh_result_timestamp("s1")
        self._advance_without_redispatch(agents)

        router.a2a = A2ATransport(rpc=StubA2AClient.from_name("path-b-a2a-fail.json"))
        router.config["a2a"]["retry_backoff_sec"] = [0, 0, 0]
        s2 = DispatchContext(
            self.tmp, "feat-auth-001", "s2", "lingzhao", 1,
            stub_fixture="path-b-a2a-fail.json",
        )
        self.assertTrue(router.dispatch_step(s2, agents).ok)
        self._refresh_result_timestamp("s2")
        with patch("lib.pipeline_routing.pick_person_for_role", return_value="dali"):
            self._advance_without_redispatch(agents)

        s3 = DispatchContext(
            self.tmp, "feat-auth-001", "s3", "dali", 8,
            stub_fixture="path-d-dali-opencode.json",
        )
        self.assertTrue(FileBusTransport(mode="stub").dispatch(s3, agents).ok)
        self._refresh_result_timestamp("s3")
        with patch("lib.pipeline_routing.resolve_next_assignee", return_value=(None, None)):
            with patch("lib.pipeline_routing.is_pipeline_terminal", return_value=True):
                trigger(self.tmp, agents, self.paths)

        task = TaskTracker(self.tmp).get("feat-auth-001")
        for sid in ("s1", "s2", "s3"):
            sr = read_step_result_file(self.tmp, "feat-auth-001", sid)
            self.assertIsNotNone(sr, sid)
            self.assertEqual(sr.get("conclusion"), "done", sid)

        completed = [
            s for s in (task.get("chain") or [])
            if isinstance(s, dict) and s.get("fsm_state") == StepFsmState.COMPLETED.value
        ]
        self.assertEqual(len(completed), 3)
        self.assertIn((task.get("fsm") or {}).get("state"), ("accepting", "succeeded"))

    def test_h05_fallback_equivalent_to_pure_file_bus(self):
        """H-05：path-b A2A 降级后与纯 file_bus 同 conclusion。"""
        agents = self._agents()
        router = TransportRouter(data_dir=self.tmp)
        router.config["a2a"]["retry_backoff_sec"] = [0, 0, 0]
        router.a2a = A2ATransport(rpc=StubA2AClient.from_name("path-b-a2a-fail.json"))
        fb_ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s2", "lingzhao", 1,
            stub_fixture="path-b-a2a-fail.json",
        )
        fallback = router.dispatch_step(fb_ctx, agents)
        self.assertTrue(fallback.ok)
        self.assertEqual(fallback.transport_used, "file_bus")
        self.assertTrue(fallback.a2a_retries_exhausted)

        pure = FileBusTransport(mode="stub").dispatch(fb_ctx, agents)
        self.assertTrue(pure.ok)

        sr_fallback = read_step_result_file(self.tmp, "feat-auth-001", "s2")
        shutil.rmtree(os.path.join(self.tmp, "msg-results", "feat-auth-001"), ignore_errors=True)
        FileBusTransport(mode="stub").dispatch(fb_ctx, agents)
        sr_pure = read_step_result_file(self.tmp, "feat-auth-001", "s2")

        self.assertEqual(sr_fallback.get("conclusion"), sr_pure.get("conclusion"))
        self.assertEqual(sr_fallback.get("summary"), sr_pure.get("summary"))


if __name__ == "__main__":
    unittest.main()
