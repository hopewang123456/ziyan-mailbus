"""TransportRouter 双通道测试（stub，零 HTTP）。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.pipeline_results import step_result_path
from lib.transport.delivery import can_deliver_a2a
from lib.transport.router import TransportRouter
from lib.transport.step_result_io import read_step_result_file
from lib.transport.stub_a2a import StubA2AClient
from lib.transport.types import DispatchContext
from lib.utils import json_write
from tests.test_helpers import load_golden_a2a_path, seed_a2a_harness


def _lingzhao_a2a_agent() -> dict:
    return {
        "type": "hermes_profile",
        "channels": {"a2a": {"enabled": True}, "file_bus": {"enabled": True}},
        "endpoint": {"base_url": "https://mailbus.example/api/a2a/rpc/lingzhao"},
        "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
    }


def _dali_filebus_agent() -> dict:
    return {
        "type": "opencode",
        "channels": {"a2a": {"enabled": False}, "file_bus": {"enabled": True}},
    }


class TestCanDeliver(unittest.TestCase):
    def test_dali_no_a2a(self):
        ctx = DispatchContext("tmp", "t1", "s3", "dali", 8)
        self.assertFalse(can_deliver_a2a("dali", _dali_filebus_agent(), ctx))

    def test_lingzhao_a2a(self):
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1)
        self.assertTrue(can_deliver_a2a("lingzhao", _lingzhao_a2a_agent(), ctx))


class TestTransportRouter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        agents = cfg.get("agents") or {}
        agents["lingzhao"] = _lingzhao_a2a_agent()
        agents["dali"] = _dali_filebus_agent()
        cfg["agents"] = agents
        cfg["harness"] = {"mode": "stub", "stub_fixtures_dir": "tests/fixtures/harness_stub"}
        json_write(cfg_path, cfg)
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "tasks", "feat-auth-001.json"),
            {
                "task_id": "feat-auth-001",
                "chain": [
                    {"step_id": "s1", "to_agent": "lingzhao", "role_type": 1},
                    {"step_id": "s2", "to_agent": "lingzhao", "role_type": 1},
                    {"step_id": "s3", "to_agent": "dali", "role_type": 8},
                ],
            },
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _router(self) -> TransportRouter:
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return TransportRouter(data_dir=self.tmp, config=cfg)

    def test_path_a_a2a_success(self):
        fixture = StubA2AClient.from_name("path-a-lingzhao-s1.json")
        router = self._router()
        router.a2a = __import__("lib.transport.a2a_standard", fromlist=["A2ATransport"]).A2ATransport(rpc=fixture)
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s1", "lingzhao", 1,
            intent="设计用户认证模块实施方案",
            stub_fixture="path-a-lingzhao-s1.json",
        )
        agents = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))["agents"]
        result = router.dispatch_step(ctx, agents)
        self.assertTrue(result.ok)
        self.assertEqual(result.transport_used, "a2a_standard")
        sr = read_step_result_file(self.tmp, "feat-auth-001", "s1")
        self.assertIsNotNone(sr)
        self.assertEqual(sr.get("conclusion"), "done")

    def test_path_b_fallback(self):
        fixture = StubA2AClient.from_name("path-b-a2a-fail.json")
        router = self._router()
        router.config["a2a"]["retry_backoff_sec"] = [0, 0, 0]
        router.a2a = __import__("lib.transport.a2a_standard", fromlist=["A2ATransport"]).A2ATransport(rpc=fixture)
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s2", "lingzhao", 1,
            stub_fixture="path-b-a2a-fail.json",
        )
        agents = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))["agents"]
        result = router.dispatch_step(ctx, agents)
        self.assertTrue(result.ok)
        self.assertEqual(result.transport_used, "file_bus")
        self.assertTrue(result.a2a_retries_exhausted)
        self.assertEqual(len([a for a in result.transport_attempts if a.get("channel") == "a2a_standard"]), 3)
        err_dir = os.path.join(self.tmp, "errors")
        self.assertTrue(any(f.startswith("a2a-fallback-") for f in os.listdir(err_dir)))

    def test_path_d_file_bus_only(self):
        router = self._router()
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s3", "dali", 8,
            stub_fixture="path-d-dali-opencode.json",
        )
        agents = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))["agents"]
        result = router.dispatch_step(ctx, agents)
        self.assertTrue(result.ok)
        self.assertEqual(result.transport_used, "file_bus")
        self.assertFalse(result.a2a_retries_exhausted)
        sr = read_step_result_file(self.tmp, "feat-auth-001", "s3")
        self.assertEqual(sr.get("normalized_from"), "opencode_replies")
        self.assertTrue(os.path.isfile(step_result_path(self.tmp, "feat-auth-001", "s3")))

    def test_path_c_input_required(self):
        fixture = StubA2AClient.from_name("path-c-input-required.json")
        router = self._router()
        router.a2a = __import__("lib.transport.a2a_standard", fromlist=["A2ATransport"]).A2ATransport(rpc=fixture)
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s1", "lingzhao", 1,
            stub_fixture="path-c-input-required.json",
        )
        agents = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))["agents"]
        result = router.dispatch_step(ctx, agents)
        self.assertFalse(result.ok)
        self.assertTrue(result.awaiting_human)
        self.assertEqual((result.human_queue_payload or {}).get("type"), "a2a_input_required")

    def test_t_r04_4xx_no_retry(self):
        """T-R04：4xx 不重试，单次 A2A 失败后立即降级 file_bus。"""
        fixture = StubA2AClient.from_name("path-http-403-fallback.json")
        router = self._router()
        router.config["a2a"]["retry_backoff_sec"] = [2, 5, 10]
        router.a2a = __import__("lib.transport.a2a_standard", fromlist=["A2ATransport"]).A2ATransport(rpc=fixture)
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s2", "lingzhao", 1,
            stub_fixture="path-http-403-fallback.json",
        )
        agents = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))["agents"]
        result = router.dispatch_step(ctx, agents)
        self.assertTrue(result.ok)
        self.assertEqual(result.transport_used, "file_bus")
        self.assertTrue(result.a2a_retries_exhausted)
        a2a_attempts = [a for a in result.transport_attempts if a.get("channel") == "a2a_standard"]
        self.assertEqual(len(a2a_attempts), 1)
        self.assertIn("403", a2a_attempts[0].get("error", ""))
        sr = read_step_result_file(self.tmp, "feat-auth-001", "s2")
        self.assertEqual(sr.get("conclusion"), "done")


if __name__ == "__main__":
    unittest.main()
