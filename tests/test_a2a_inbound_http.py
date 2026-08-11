"""from_a2a_task_create 与 HttpA2AClient 单测。"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.a2a.a2a_mapper import from_a2a_task_create, to_a2a_hub_task
from lib.core.a2a.http_a2a import HttpA2AClient
from lib.core.a2a.errors import RetryableTransportError
from lib.application.orchestration.router.planner import plan_tier0


class TestFromA2ATaskCreate(unittest.TestCase):
    def test_maps_send_message_to_envelope(self):
        env = from_a2a_task_create({
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "实现 JWT 认证"}],
                "metadata": {
                    "mailbus": {
                        "taskType": "feature",
                        "tier": "M",
                        "initiator": "external",
                    }
                },
            }
        })
        self.assertEqual(env["intent"], "实现 JWT 认证")
        self.assertEqual(env["task_type"], "feature")
        self.assertEqual(env["initiator"], "external")
        self.assertTrue(env["task_id"].startswith("ext-"))

    def test_preserves_task_id(self):
        env = from_a2a_task_create({
            "message": {
                "parts": [{"text": "hi"}],
                "metadata": {"mailbus": {"taskId": "feat-ext-001"}},
            }
        })
        self.assertEqual(env["task_id"], "feat-ext-001")


class TestCodeReviewPlanner(unittest.TestCase):
    def test_warn_adds_acceptance(self):
        out = plan_tier0({
            "mode": "auto",
            "task_type": "code_review",
            "tier": "S",
            "extensions": {"harness": {"aggregate_status": "warn", "layers": {}}},
        })
        rts = [x["role_type"] for x in out["planned_chain"]]
        self.assertEqual(rts[0], 5)
        self.assertIn(12, rts)

    def test_security_finding_adds_lingjin(self):
        out = plan_tier0({
            "mode": "auto",
            "task_type": "code_review",
            "tier": "S",
            "extensions": {
                "harness": {
                    "aggregate_status": "warn",
                    "layers": {"static_analysis": {"semgrep": {"findings": 2}}},
                }
            },
        })
        rts = [x["role_type"] for x in out["planned_chain"]]
        self.assertIn(7, rts)


class TestHubTaskMapping(unittest.TestCase):
    def test_final_acceptance_maps_input_required(self):
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

    def test_pending_hq_a2a_input_required(self):
        task = {"task_id": "feat-002", "fsm": {"state": "executing"}}
        hq = [{
            "id": "hq-1",
            "type": "a2a_input_required",
            "status": "pending",
            "task_id": "feat-002",
            "title": "需确认",
            "context": {"prompt": "OAuth2 还是 JWT?"},
        }]
        wire = to_a2a_hub_task(task, "a2a-abc", human_queue=hq)
        self.assertEqual(wire["status"], "input-required")
        self.assertEqual(wire["metadata"]["mailbus"]["hqType"], "a2a_input_required")
        self.assertIn("JWT", wire.get("statusMessage", ""))


class TestHttpA2AClient(unittest.TestCase):
    def test_send_message_parses_task_id(self):
        client = HttpA2AClient("https://example.test/rpc")
        payload_holder = {}

        def fake_urlopen(req, timeout=0):
            payload_holder["url"] = req.full_url
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["method"], "SendMessage")
            resp = MagicMock()
            resp.read.return_value = json.dumps({
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"task": {"id": "a2a-remote-1", "status": "working"}},
            }).encode("utf-8")
            resp.__enter__ = lambda s: resp
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("lib.core.a2a.http_a2a.urlrequest.urlopen", fake_urlopen):
            out = client.send_message({
                "task_id": "t1", "step_id": "s1", "to_agent": "lingzhao",
                "role_type": 1, "intent": "hello",
            })
        self.assertEqual(out["task"]["id"], "a2a-remote-1")
        self.assertEqual(client.task_id, "a2a-remote-1")

    def test_retryable_on_503(self):
        client = HttpA2AClient("https://example.test/rpc")
        import urllib.error

        def fake_urlopen(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 503, "unavailable", {}, None)

        with patch("lib.core.a2a.http_a2a.urlrequest.urlopen", fake_urlopen):
            with self.assertRaises(RetryableTransportError):
                client.send_message({"intent": "x", "task_id": "t", "step_id": "s1", "to_agent": "a", "role_type": 1})


if __name__ == "__main__":
    unittest.main()
