"""A2A Transport 集成测试 — stub JSON-RPC 与 Router 接线。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.frameworks import get_adapter
from lib.core.a2a.a2a_standard import A2ATransport
from lib.core.a2a.dispatch_integration import build_router, transport_router_enabled
from lib.core.a2a.router import TransportRouter
from lib.core.a2a.stub_a2a import StubA2AClient
from lib.core.a2a.types import DispatchContext
from lib.infra.utils import json_write
from tests.test_helpers import seed_a2a_harness


class TestA2ATransport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("agents", {})["lingzhao"] = {
            "type": "hermes_profile",
            "role_types": [1],
            "channels": {"a2a": {"enabled": True}, "file_bus": {"enabled": True}},
            "endpoint": {"base_url": "https://mailbus.example/api/a2a/rpc/lingzhao"},
            "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
        }
        cfg["transport"] = {"use_router": True, "a2a": {"retry_backoff_sec": [0, 0, 0]}}
        json_write(cfg_path, cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a2a_remote_adapter_registered(self):
        adapter = get_adapter("a2a_remote")
        self.assertIsNotNone(adapter)
        self.assertTrue(hasattr(adapter, "can_deliver_a2a"))

    def test_build_router_when_enabled(self):
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertTrue(transport_router_enabled(cfg))
        router = build_router(self.tmp)
        self.assertIsInstance(router, TransportRouter)

    def test_dispatch_once_completed(self):
        fixture = StubA2AClient.from_name("path-a-lingzhao-s1.json")
        transport = A2ATransport(rpc=fixture)
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s1", "lingzhao", 1,
            stub_fixture="path-a-lingzhao-s1.json",
        )
        out = transport.dispatch_once(ctx, {})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("step_result", {}).get("conclusion"), "done")


if __name__ == "__main__":
    unittest.main()
