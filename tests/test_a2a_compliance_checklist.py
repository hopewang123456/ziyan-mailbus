"""A2A Compliance Spec §10 检查清单聚合测试（零 HTTP）。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.harness import get_harness
from lib.adapters.orchestration.task_fsm import apply_submit, read_step_result, write_step_result
from lib.core.a2a.a2a_mapper import to_a2a_hub_task, to_a2a_message
from lib.core.a2a.a2a_standard import A2ATransport
from lib.core.a2a.agent_card_cache import enrich_agent_channels, load_registry
from lib.core.a2a.a2a_mapper import to_agent_card
from lib.core.a2a.delivery import can_deliver_a2a
from lib.core.a2a.file_bus import FileBusTransport
from lib.core.a2a.router import TransportRouter
from lib.core.a2a.step_result_io import read_step_result_file
from lib.core.a2a.stub_a2a import StubA2AClient
from lib.core.a2a.types import DispatchContext
from lib.infra.utils import json_read, json_write
from tests.test_helpers import load_golden_a2a_path, seed_a2a_harness


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


class TestA2AComplianceChecklist(unittest.TestCase):
    """a2a-compliance-spec.md §10 第一性原则 — 每项至少一条断言。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_fsm_reads_canonical_step_result(self):
        """FSM 只读 canonical step-{step_id}.json，legacy 单文件不参与。"""
        os.makedirs(os.path.join(self.tmp, "msg-results", "t1"), exist_ok=True)
        step = {"step": 1, "step_id": "s1", "to_person": "lingzhao", "to_agent": "lingzhao"}
        canonical = {
            "task_id": "t1",
            "step_id": "s1",
            "agent": "lingzhao",
            "pipeline_step": 1,
            "conclusion": "done",
            "summary": "canonical",
        }
        write_step_result(self.tmp, "t1", step, canonical)
        json_write(
            os.path.join(self.tmp, "msg-results", "t1.json"),
            {"task_id": "t1", "agent": "lingzhao", "conclusion": "done", "summary": "legacy-only"},
        )
        cfg_path = os.path.join(self.tmp, "config.json")
        json_write(cfg_path, {"mailbus_automation": {"legacy_result_read": False}})

        got = read_step_result(self.tmp, "t1", step)
        self.assertEqual(got.get("summary"), "canonical")

        task = {
            "task_id": "t1",
            "status": "running",
            "chain": [{
                **step,
                "status": "running",
                "fsm_state": "awaiting_result",
                "planned_agents": ["lingxi"],
            }],
        }
        out = apply_submit(task, canonical, agents={"lingxi": {}, "lingzhao": {}})
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "advance")

    def test_02_a2a_three_retries_then_file_bus(self):
        """A2A 失败 3 次后降级 file_bus 且 a2a_retries_exhausted。"""
        seed_a2a_harness(self.tmp)
        cfg_path = os.path.join(self.tmp, "config.json")
        cfg = json_read(cfg_path, {})
        cfg.setdefault("agents", {})["lingzhao"] = _lingzhao_agent()
        cfg["a2a"] = {"max_retries": 3, "retry_backoff_sec": [0, 0, 0]}
        json_write(cfg_path, cfg)
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "tasks", "feat-auth-001.json"),
            {"task_id": "feat-auth-001", "chain": [{"step_id": "s2", "to_agent": "lingzhao"}]},
        )

        golden = load_golden_a2a_path("b")
        self.assertTrue(golden["transport_audit"]["a2a_retries_exhausted"])

        router = TransportRouter(data_dir=self.tmp)
        router.config["a2a"]["retry_backoff_sec"] = [0, 0, 0]
        router.a2a = A2ATransport(rpc=StubA2AClient.from_name("path-b-a2a-fail.json"))
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s2", "lingzhao", 1,
            stub_fixture="path-b-a2a-fail.json",
        )
        result = router.dispatch_step(ctx, cfg["agents"])
        self.assertTrue(result.ok)
        self.assertEqual(result.transport_used, "file_bus")
        self.assertTrue(result.a2a_retries_exhausted)
        a2a_fails = [
            a for a in result.transport_attempts
            if a.get("channel") == "a2a_standard" and a.get("outcome") == "fail"
        ]
        self.assertEqual(len(a2a_fails), 3)

    def test_03_transport_attempts_persisted_on_chain(self):
        """每步 dispatch 后 task.json chain 写入 transport_attempts。"""
        seed_a2a_harness(self.tmp)
        cfg_path = os.path.join(self.tmp, "config.json")
        cfg = json_read(cfg_path, {})
        cfg.setdefault("agents", {})["lingzhao"] = _lingzhao_agent()
        json_write(cfg_path, cfg)
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "tasks", "feat-auth-001.json"),
            {"task_id": "feat-auth-001", "chain": [{"step_id": "s1", "to_agent": "lingzhao"}]},
        )

        router = TransportRouter(data_dir=self.tmp)
        router.a2a = A2ATransport(rpc=StubA2AClient.from_name("path-a-lingzhao-s1.json"))
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s1", "lingzhao", 1,
            stub_fixture="path-a-lingzhao-s1.json",
        )
        router.dispatch_step(ctx, cfg["agents"])

        task = json_read(os.path.join(self.tmp, "tasks", "feat-auth-001.json"), {})
        step = task["chain"][0]
        self.assertEqual(step["transport_used"], "a2a_standard")
        self.assertIsInstance(step.get("transport_attempts"), list)
        self.assertGreaterEqual(len(step["transport_attempts"]), 1)

    def test_04_cli_agent_card_visible_a2a_disabled(self):
        """CLI agent（dali）Card 可见但 channels.a2a.enabled=false，can_deliver 为 false。"""
        registry = load_registry()
        entry = enrich_agent_channels("dali", dict(registry.get("dali") or {}))
        self.assertFalse((entry.get("channels") or {}).get("a2a", {}).get("enabled", True))

        card = to_agent_card("dali", entry, display_name="大力")
        self.assertEqual(card["metadata"]["mailbus"]["agent_id"], "dali")
        self.assertEqual(card["metadata"]["mailbus"]["transport_default"], "file_bus")
        self.assertEqual(card.get("supportedInterfaces"), [])

        ctx = DispatchContext(self.tmp, "t1", "s1", "dali", 8)
        self.assertFalse(can_deliver_a2a("dali", entry, ctx))

    def test_05_dali_normalize_before_pipeline(self):
        """dali file_bus 交付经 normalize 再写入 canonical step-result。"""
        seed_a2a_harness(self.tmp)
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s3", "dali", 8,
            stub_fixture="path-d-dali-opencode.json",
        )
        result = FileBusTransport(mode="stub").dispatch(ctx, {})
        self.assertTrue(result.ok)
        sr = read_step_result_file(self.tmp, "feat-auth-001", "s3")
        self.assertEqual(sr.get("normalized_from"), "opencode_replies")
        self.assertEqual(sr.get("conclusion"), "done")

        golden = load_golden_a2a_path("d")
        self.assertEqual(
            sr.get("normalized_from"),
            golden["canonical_step_result"].get("normalized_from"),
        )

    def test_06_final_acceptance_maps_input_required(self):
        """final_acceptance 对外 A2A 聚合为 input-required。"""
        task = {
            "task_id": "feat-001",
            "task_type": "feature",
            "tier": "M",
            "intent": "demo",
            "fsm": {"state": "accepting"},
        }
        wire = to_a2a_hub_task(task, "a2a-hub-1")
        self.assertEqual(wire["status"], "input-required")
        self.assertEqual(wire["metadata"]["mailbus"]["hqType"], "final_acceptance")

    def test_07_resolve_uses_role_agent(self):
        """human-queue resolve 以 role 身份续发 SendMessage（ROLE_AGENT）。"""
        golden_c = load_golden_a2a_path("c")
        msg = golden_c["wire"]["resolve_send_message"]["params"]["message"]
        self.assertEqual(msg["role"], "ROLE_AGENT")
        self.assertEqual(msg["metadata"]["mailbus"]["agentId"], "lingzhao")

        golden_a = load_golden_a2a_path("a")
        user_msg = to_a2a_message(golden_a["canonical_dispatch"])
        self.assertEqual(user_msg["role"], "ROLE_USER")


class TestHarnessRecordReplay(unittest.TestCase):
    """harness-runtime-spec §3 record/replay。"""

    def test_record_mode_returns_record_harness(self):
        cfg = {"harness": {"mode": "record"}}
        harness = get_harness(cfg)
        self.assertEqual(type(harness).__name__, "RecordHarness")

    def test_replay_mode_roundtrip(self):
        cfg = {"harness": {"mode": "replay", "stub_fixtures_dir": "tests/fixtures/harness_stub"}}
        harness = get_harness(cfg)
        self.assertEqual(type(harness).__name__, "ReplayHarness")
        session = harness.spawn(
            "dali",
            {"task_id": "feat-auth-001", "step_id": "s3"},
        )
        outcome = harness.wait_completion(session)
        self.assertTrue(outcome.ok)
        self.assertTrue(outcome.ack_received)
        self.assertIsNotNone(outcome.step_result)
        self.assertEqual(outcome.step_result.get("agent"), "dali")
        self.assertEqual(outcome.step_result.get("conclusion"), "done")
        self.assertEqual(outcome.step_result.get("normalized_from"), "opencode_replies")


if __name__ == "__main__":
    unittest.main()
