"""human-queue a2a_input_required resolve 闭环测试。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.orchestration.human_queue import enqueue, load_queue
from lib.application.orchestration.human_queue_resolve import resolve_human_queue_item
from lib.core.a2a.step_result_io import read_step_result_file
from lib.core.a2a.stub_a2a import StubA2AClient
from lib.core.a2a.a2a_standard import A2ATransport
from lib.core.a2a.router import TransportRouter
from lib.core.a2a.types import DispatchContext
from lib.infra.utils import json_write
from tests.test_helpers import load_golden_a2a_path, seed_a2a_harness


def _lingzhao_agent():
    return {
        "type": "hermes_profile",
        "role_types": [1],
        "channels": {"a2a": {"enabled": True}, "file_bus": {"enabled": True}},
        "endpoint": {"base_url": "https://mailbus.example/api/a2a/rpc/lingzhao"},
        "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
    }


class TestHumanQueueA2A(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("agents", {})["lingzhao"] = _lingzhao_agent()
        cfg["harness"] = {"mode": "stub"}
        cfg["transport"] = {"use_router": True, "a2a": {"retry_backoff_sec": [0, 0, 0]}}
        json_write(cfg_path, cfg)
        golden = load_golden_a2a_path("c")
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "tasks", "feat-auth-001.json"),
            {
                "task_id": "feat-auth-001",
                "chain": [{"step_id": "s1", "to_agent": "lingzhao", "role_type": 1}],
            },
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolve_continues_a2a_path_c(self):
        fixture = StubA2AClient.from_name("path-c-input-required.json")
        router = TransportRouter(data_dir=self.tmp)
        router.a2a = A2ATransport(rpc=fixture)
        ctx = DispatchContext(
            self.tmp, "feat-auth-001", "s1", "lingzhao", 1,
            stub_fixture="path-c-input-required.json",
        )
        agents = json.load(open(os.path.join(self.tmp, "config.json"), encoding="utf-8"))["agents"]
        first = router.dispatch_step(ctx, agents)
        self.assertTrue(first.awaiting_human)
        doc = load_queue(self.tmp)
        pending = next(
            i for i in (doc.get("items") or [])
            if i.get("status") == "pending" and i.get("type") == "a2a_input_required"
        )

        item, side = resolve_human_queue_item(
            self.tmp,
            pending["id"],
            {
                "decision": "approved",
                "reviewer": "lingzhao",
                "comment": "采用自建 JWT + refresh，不用 OAuth2。",
            },
        )
        self.assertIsNotNone(item)
        self.assertTrue(side.get("ok"))
        sr = read_step_result_file(self.tmp, "feat-auth-001", "s1")
        self.assertIsNotNone(sr)
        self.assertEqual(sr.get("conclusion"), "done")


if __name__ == "__main__":
    unittest.main()
