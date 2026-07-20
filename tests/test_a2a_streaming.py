"""SendStreamingMessage SSE 客户端与入站 RPC 单测。"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.handlers_a2a import handle_a2a_rpc
from lib.transport.a2a_standard import A2ATransport
from lib.transport.a2a_stream import (
    build_status_update_result,
    iter_stream_events,
    iter_stream_status_updates,
    is_stream_terminal,
)
from lib.transport.config import resolve_use_streaming
from lib.transport.dispatch_integration import merge_agent_transport_config
from lib.transport.errors import NonRetryableTransportError
from lib.transport.http_a2a import (
    HttpA2AClient,
    _aggregate_streaming_result,
    _parse_sse_jsonrpc_events,
)
from lib.transport.types import DispatchContext
from lib.utils import json_write
from tests.test_helpers import seed_a2a_harness


class TestSseParsing(unittest.TestCase):
    def test_parse_sse_jsonrpc_events(self):
        raw = (
            "data: {\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"id\":\"t1\",\"status\":\"working\"}}\n\n"
            "data: {\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"taskId\":\"t1\",\"status\":{\"state\":\"completed\"},\"final\":true}}\n\n"
        )
        events = _parse_sse_jsonrpc_events(raw)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["result"]["id"], "t1")

    def test_aggregate_task_and_status_updates(self):
        events = [
            {"jsonrpc": "2.0", "id": "1", "result": {"id": "t1", "status": "working"}},
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "taskId": "t1",
                    "status": {"state": "completed", "message": "done"},
                    "final": True,
                },
            },
        ]
        out = _aggregate_streaming_result(events)
        self.assertEqual(out["task"]["id"], "t1")
        self.assertEqual(out["task"]["status"], "completed")
        self.assertEqual(out["task"]["statusMessage"], "done")


class TestHttpA2AStreamingClient(unittest.TestCase):
    def test_send_streaming_message_sse(self):
        client = HttpA2AClient("https://example.test/rpc")

        def fake_urlopen(req, timeout=0):
            self.assertIn("text/event-stream", req.headers.get("Accept", ""))
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["method"], "SendStreamingMessage")
            sse = (
                f'data: {{"jsonrpc":"2.0","id":"{body["id"]}","result":{{"id":"a2a-stream-1","status":"working"}}}}\n\n'
                f'data: {{"jsonrpc":"2.0","id":"{body["id"]}","result":{{"taskId":"a2a-stream-1","status":{{"state":"completed"}},"final":true}}}}\n\n'
            )
            resp = MagicMock()
            resp.headers = {"Content-Type": "text/event-stream"}
            resp.read.return_value = sse.encode("utf-8")
            resp.__enter__ = lambda s: resp
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("lib.transport.http_a2a.urlrequest.urlopen", fake_urlopen):
            out = client.send_streaming_message({
                "task_id": "t1", "step_id": "s1", "to_agent": "lingzhao",
                "role_type": 1, "intent": "hello",
            })
        self.assertEqual(out["task"]["id"], "a2a-stream-1")
        self.assertEqual(out["task"]["status"], "completed")
        self.assertEqual(client.task_id, "a2a-stream-1")

    def test_send_streaming_message_fallback(self):
        client = HttpA2AClient("https://example.test/rpc")
        calls = []

        def fake_urlopen(req, timeout=0):
            calls.append(json.loads(req.data.decode("utf-8"))["method"])
            body = json.loads(req.data.decode("utf-8"))
            if body["method"] == "SendStreamingMessage":
                resp = MagicMock()
                resp.read.return_value = json.dumps({
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32601, "message": "method_not_found"},
                }).encode("utf-8")
                resp.headers = {"Content-Type": "application/json"}
                resp.__enter__ = lambda s: resp
                resp.__exit__ = MagicMock(return_value=False)
                return resp
            resp = MagicMock()
            resp.read.return_value = json.dumps({
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"task": {"id": "fallback-1", "status": "working"}},
            }).encode("utf-8")
            resp.headers = {"Content-Type": "application/json"}
            resp.__enter__ = lambda s: resp
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("lib.transport.http_a2a.urlrequest.urlopen", fake_urlopen):
            out = client.send_streaming_message({
                "task_id": "t1", "step_id": "s1", "to_agent": "lingzhao",
                "role_type": 1, "intent": "hello",
            })
        self.assertEqual(calls, ["SendStreamingMessage", "SendMessage"])
        self.assertEqual(out["task"]["id"], "fallback-1")

    def test_empty_stream_raises(self):
        client = HttpA2AClient("https://example.test/rpc")

        def fake_urlopen(req, timeout=0):
            resp = MagicMock()
            resp.headers = {"Content-Type": "text/event-stream"}
            resp.read.return_value = b""
            resp.__enter__ = lambda s: resp
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("lib.transport.http_a2a.urlrequest.urlopen", fake_urlopen):
            with self.assertRaises(NonRetryableTransportError):
                client.send_streaming_message({
                    "task_id": "t1", "step_id": "s1", "to_agent": "a",
                    "role_type": 1, "intent": "x",
                })


class MockStreamingClient:
    """模拟 HttpA2AClient 的 streaming 行为。"""

    def __init__(self, *, terminal: bool = True, fail_stream: bool = False):
        self.terminal = terminal
        self.fail_stream = fail_stream
        self.task_id = ""
        self.calls: list[str] = []

    def send_streaming_message(self, dispatch: dict) -> dict:
        self.calls.append("send_streaming_message")
        if self.fail_stream:
            raise NonRetryableTransportError("method_not_found", code="-32601")
        status = "completed" if self.terminal else "working"
        self.task_id = "stream-task-1"
        return {"task": {"id": self.task_id, "status": status, "statusMessage": "done"}}

    def send_message(self, dispatch: dict) -> dict:
        self.calls.append("send_message")
        self.task_id = "fallback-task-1"
        return {"task": {"id": self.task_id, "status": "working"}}

    def poll_task(self) -> dict:
        self.calls.append("poll_task")
        return {"id": self.task_id, "status": "completed", "statusMessage": "done"}

    def is_terminal(self, task: dict) -> bool:
        return (task.get("status") or "").lower() in (
            "completed", "failed", "canceled", "cancelled",
        )


class TestA2ATransportStreaming(unittest.TestCase):
    def test_dispatch_once_uses_streaming_when_enabled(self):
        client = MockStreamingClient(terminal=True)
        transport = A2ATransport(
            rpc=client,
            config={"transport": {"a2a": {"use_streaming": True}}},
        )
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        out = transport.dispatch_once(ctx, {})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("a2a_task_id"), "stream-task-1")
        self.assertEqual(client.calls, ["send_streaming_message"])
        self.assertNotIn("poll_task", client.calls)

    def test_dispatch_once_streaming_fallback_to_send_message(self):
        client = MockStreamingClient(fail_stream=True, terminal=False)
        transport = A2ATransport(
            rpc=client,
            config={"transport": {"a2a": {"use_streaming": True}}},
        )
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        out = transport.dispatch_once(ctx, {})
        self.assertTrue(out.get("ok"))
        self.assertEqual(client.calls[:2], ["send_streaming_message", "send_message"])
        self.assertIn("poll_task", client.calls)

    def test_dispatch_once_default_uses_send_message(self):
        client = MockStreamingClient()
        transport = A2ATransport(rpc=client, config={"transport": {"a2a": {}}})
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        transport.dispatch_once(ctx, {})
        self.assertEqual(client.calls[0], "send_message")

    def test_dispatch_async_uses_streaming_when_enabled(self):
        client = MockStreamingClient(terminal=True)
        transport = A2ATransport(
            rpc=client,
            config={"transport": {"a2a": {"use_streaming": True}}},
        )
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        out = transport.dispatch_async(ctx, {})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("a2a_task_id"), "stream-task-1")
        self.assertEqual(client.calls, ["send_streaming_message"])

    def test_dispatch_async_streaming_fallback_to_send_message(self):
        client = MockStreamingClient(fail_stream=True)
        transport = A2ATransport(
            rpc=client,
            config={"transport": {"a2a": {"use_streaming": True}}},
        )
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        out = transport.dispatch_async(ctx, {})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("a2a_task_id"), "fallback-task-1")
        self.assertEqual(client.calls, ["send_streaming_message", "send_message"])

    def test_dispatch_once_agent_use_streaming_overrides_global_false(self):
        client = MockStreamingClient(terminal=True)
        transport = A2ATransport(
            rpc=client,
            config={"transport": {"a2a": {"use_streaming": False}}},
        )
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        agents = {"lingzhao": {"channels": {"a2a": {"use_streaming": True}}}}
        transport.dispatch_once(ctx, agents)
        self.assertEqual(client.calls, ["send_streaming_message"])

    def test_dispatch_once_agent_use_streaming_overrides_global_true(self):
        client = MockStreamingClient()
        transport = A2ATransport(
            rpc=client,
            config={"transport": {"a2a": {"use_streaming": True}}},
        )
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        agents = {"lingzhao": {"channels": {"a2a": {"use_streaming": False}}}}
        transport.dispatch_once(ctx, agents)
        self.assertEqual(client.calls[0], "send_message")

    def test_dispatch_async_agent_use_streaming_overrides_global(self):
        client = MockStreamingClient(terminal=True)
        transport = A2ATransport(
            rpc=client,
            config={"transport": {"a2a": {"use_streaming": False}}},
        )
        ctx = DispatchContext("tmp", "t1", "s1", "lingzhao", 1, intent="hello")
        agents = {"lingzhao": {"channels": {"a2a": {"use_streaming": True}}}}
        transport.dispatch_async(ctx, agents)
        self.assertEqual(client.calls, ["send_streaming_message"])


class TestResolveUseStreaming(unittest.TestCase):
    def test_agent_override_takes_precedence(self):
        cfg = {"transport": {"a2a": {"use_streaming": True}}}
        agent = {"channels": {"a2a": {"use_streaming": False}}}
        self.assertFalse(resolve_use_streaming(cfg, agent))

    def test_falls_back_to_global_when_agent_unset(self):
        cfg = {"transport": {"a2a": {"use_streaming": True}}}
        agent = {"channels": {"a2a": {"enabled": True}}}
        self.assertTrue(resolve_use_streaming(cfg, agent))

    def test_merge_agent_transport_config_preserves_use_streaming(self):
        agents = merge_agent_transport_config({
            "lingzhao": {
                "framework": "hermes_profile",
                "channels": {"a2a": {"use_streaming": True}},
            },
        })
        self.assertTrue(
            agents["lingzhao"]["channels"]["a2a"]["use_streaming"],
        )
        self.assertTrue(
            agents["lingzhao"]["channels"]["a2a"].get("enabled"),
        )


class MockStreamingHandler:
    data_dir = ""
    agents = {}
    headers: dict = {}

    def __init__(self, data_dir, *, accept: str = "text/event-stream"):
        self.data_dir = data_dir
        self.agents = {}
        self.headers = {"Accept": accept}
        self._body = {}
        self._resp_json = None
        self._resp_status = 200
        self._wfile = io.BytesIO()

    @property
    def wfile(self):
        return self._wfile

    def _read_post_body(self):
        return self._body

    def _send_json(self, data, status=200):
        self._resp_json = (data, status)

    def _send_sse_start(self, status=200, *, http_status=None):
        self._resp_status = http_status if http_status is not None else status
        self._sse = True

    def _send_sse_jsonrpc(self, rpc_id, result, *, error=None):
        doc = {"jsonrpc": "2.0", "id": rpc_id}
        if error:
            doc["error"] = error
        else:
            doc["result"] = result
        payload = json.dumps(doc, ensure_ascii=False)
        self._wfile.write(f"data: {payload}\n\n".encode("utf-8"))

    def _send_sse_comment(self, comment: str = "keepalive"):
        self._wfile.write(f": {comment}\n\n".encode("utf-8"))


class TestInboundSendStreamingMessage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mock_create_ok(self, handler, agent_id, params):
        return {
            "id": "a2a-inbound-1",
            "status": "working",
            "metadata": {"mailbus": {"taskId": "feat-ext-001", "stepId": "s1"}},
        }, 201, None

    @patch("lib.transport.a2a_stream.iter_stream_events", return_value=iter([]))
    @patch("lib.api.handlers_a2a._create_a2a_wire_task")
    def test_inbound_sse_creates_task(self, mock_create, _mock_iter):
        mock_create.side_effect = self._mock_create_ok
        handler = MockStreamingHandler(self.tmp, accept="text/event-stream")
        handler._body = {
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "method": "SendStreamingMessage",
            "params": {
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "流式任务测试"}],
                    "metadata": {"mailbus": {"taskType": "feature", "tier": "S"}},
                }
            },
        }
        handle_a2a_rpc(handler, "lingzhao")
        mock_create.assert_called_once()
        self.assertTrue(getattr(handler, "_sse", False))
        raw = handler._wfile.getvalue().decode("utf-8")
        self.assertIn("data:", raw)
        events = _parse_sse_jsonrpc_events(raw)
        self.assertEqual(len(events), 1)
        task = events[0]["result"]
        self.assertEqual(task["status"], "working")
        self.assertEqual(task["id"], "a2a-inbound-1")

    @patch("lib.transport.a2a_stream.time.sleep")
    @patch("lib.api.handlers_a2a._create_a2a_wire_task")
    def test_inbound_sse_pushes_status_updates(self, mock_create, _mock_sleep):
        mock_create.side_effect = self._mock_create_ok
        json_write(
            os.path.join(self.tmp, "tasks", "feat-ext-001.json"),
            {
                "task_id": "feat-ext-001",
                "intent": "流式任务测试",
                "fsm": {"state": "executing"},
                "chain": [{"step_id": "s1", "a2a_task_id": "a2a-inbound-1"}],
            },
        )
        reads = {"n": 0}

        def fake_iter(data_dir, wire_task, **kwargs):
            reads["n"] += 1
            if reads["n"] == 1:
                yield {
                    "kind": "update",
                    "hub": {
                        "id": "a2a-inbound-1",
                        "status": "completed",
                        "statusMessage": "done",
                    },
                    "final": True,
                }
            return

        handler = MockStreamingHandler(self.tmp, accept="text/event-stream")
        handler._body = {
            "jsonrpc": "2.0",
            "id": "rpc-stream",
            "method": "SendStreamingMessage",
            "params": {"message": {"parts": [{"text": "x"}]}},
        }
        with patch("lib.transport.a2a_stream.iter_stream_events", side_effect=fake_iter):
            handle_a2a_rpc(handler, "lingzhao")
        events = _parse_sse_jsonrpc_events(handler._wfile.getvalue().decode("utf-8"))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["result"]["status"], "working")
        upd = events[1]["result"]
        self.assertEqual(upd["taskId"], "a2a-inbound-1")
        self.assertEqual(upd["status"]["state"], "completed")
        self.assertTrue(upd["final"])

    @patch("lib.transport.a2a_stream.iter_stream_status_updates")
    @patch("lib.api.handlers_a2a._create_a2a_wire_task")
    def test_inbound_json_accept_aggregates(self, mock_create, mock_iter):
        mock_create.side_effect = self._mock_create_ok
        hub = {"id": "a2a-inbound-1", "status": "completed", "statusMessage": "done"}
        mock_iter.return_value = iter([(hub, True)])
        handler = MockStreamingHandler(self.tmp, accept="application/json")
        handler._body = {
            "jsonrpc": "2.0",
            "id": "rpc-2",
            "method": "SendStreamingMessage",
            "params": {
                "message": {
                    "parts": [{"text": "聚合返回"}],
                    "metadata": {"mailbus": {"taskType": "feature", "tier": "S"}},
                }
            },
        }
        handle_a2a_rpc(handler, "lingzhao")
        self.assertIsNotNone(handler._resp_json)
        data, status = handler._resp_json
        self.assertEqual(status, 201)
        self.assertEqual(data["result"]["task"]["status"], "completed")
        self.assertEqual(data["result"]["task"]["id"], "a2a-inbound-1")
        self.assertEqual(data["result"]["task"]["statusMessage"], "done")


class TestA2AStreamHelpers(unittest.TestCase):
    def test_build_status_update_result(self):
        upd = build_status_update_result("tid-1", {"status": "input-required", "statusMessage": "需确认"}, final=True)
        self.assertEqual(upd["taskId"], "tid-1")
        self.assertEqual(upd["status"]["state"], "input-required")
        self.assertTrue(upd["final"])

    def test_is_stream_terminal(self):
        self.assertTrue(is_stream_terminal("completed"))
        self.assertFalse(is_stream_terminal("working"))


class TestIterStreamEvents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wire(self, *, task_id: str = "feat-ext-001", status: str = "working") -> dict:
        return {
            "id": "a2a-stream-1",
            "status": status,
            "metadata": {"mailbus": {"taskId": task_id, "stepId": "s1"}},
        }

    @patch("lib.transport.a2a_stream._stream_config")
    @patch("lib.transport.a2a_stream.time.sleep")
    @patch("lib.transport.a2a_stream.resolve_hub_wire")
    def test_yields_heartbeat_between_polls(self, mock_resolve, _mock_sleep, mock_cfg):
        mock_cfg.return_value = {
            "tick": 0.1,
            "timeout": 60.0,
            "heartbeat": 1.0,
            "max_events": 0,
            "missing_grace": 0.3,
        }
        mock_resolve.return_value = {"status": "working", "statusMessage": ""}
        clock = {"t": 0.0}

        def mono():
            clock["t"] += 1.0
            return clock["t"]

        with patch("lib.transport.a2a_stream.time.monotonic", side_effect=mono):
            events = []
            for event in iter_stream_events(
                self.tmp,
                self._wire(),
                tick_sec=0.1,
                timeout_sec=3,
            ):
                events.append(event)
                if event.get("kind") == "heartbeat":
                    break
        self.assertEqual(events[-1]["kind"], "heartbeat")
        self.assertFalse(any(e.get("kind") == "update" for e in events))

    @patch("lib.transport.a2a_stream._stream_config")
    @patch("lib.transport.a2a_stream.time.sleep")
    @patch("lib.transport.a2a_stream.resolve_hub_wire")
    def test_missing_task_closes_after_grace(self, mock_resolve, _mock_sleep, mock_cfg):
        mock_cfg.return_value = {
            "tick": 0.05,
            "timeout": 60.0,
            "heartbeat": 0.0,
            "max_events": 0,
            "missing_grace": 0.3,
        }
        mock_resolve.return_value = None
        times = iter([0.0, 0.0, 0.05, 0.05, 0.35, 0.35])
        with patch("lib.transport.a2a_stream.time.monotonic", side_effect=lambda: next(times, 999.0)):
            events = list(iter_stream_events(
                self.tmp,
                self._wire(),
                tick_sec=0.05,
                timeout_sec=60,
            ))
        self.assertEqual(events, [])

    @patch("lib.transport.a2a_stream.time.sleep")
    @patch("lib.transport.a2a_stream.resolve_hub_wire")
    def test_terminal_without_change_closes_immediately(self, mock_resolve, _mock_sleep):
        mock_resolve.return_value = {"status": "completed", "statusMessage": "done"}
        events = list(iter_stream_events(
            self.tmp,
            self._wire(status="completed"),
            tick_sec=0.1,
            timeout_sec=60,
        ))
        self.assertEqual(events, [])

    @patch("lib.transport.a2a_stream.time.sleep")
    @patch("lib.transport.a2a_stream.resolve_hub_wire")
    def test_status_update_and_terminal(self, mock_resolve, _mock_sleep):
        mock_resolve.return_value = {"status": "completed", "statusMessage": "done"}
        events = list(iter_stream_events(
            self.tmp,
            self._wire(),
            tick_sec=0.1,
            timeout_sec=60,
        ))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "update")
        self.assertTrue(events[0]["final"])

    @patch("lib.transport.a2a_stream._stream_config")
    @patch("lib.transport.a2a_stream.time.sleep")
    @patch("lib.transport.a2a_stream.resolve_hub_wire")
    def test_stream_max_events_emits_timeout_final(self, mock_resolve, _mock_sleep, mock_cfg):
        mock_cfg.return_value = {
            "tick": 0.1,
            "timeout": 60.0,
            "heartbeat": 0.0,
            "max_events": 1,
            "missing_grace": 0.3,
        }
        mock_resolve.return_value = {"status": "executing", "statusMessage": "mid"}
        events = list(iter_stream_status_updates(
            self.tmp,
            self._wire(),
            tick_sec=0.05,
            timeout_sec=5,
        ))
        self.assertEqual(len(events), 2)
        self.assertFalse(events[0][1])
        self.assertEqual(events[0][0]["status"], "executing")
        self.assertTrue(events[1][1])
        self.assertIn("stream timeout", events[1][0]["statusMessage"])

    @patch("lib.transport.a2a_stream.iter_stream_events")
    @patch("lib.api.handlers_a2a._create_a2a_wire_task")
    def test_inbound_sse_sends_heartbeat_comment(self, mock_create, mock_iter):
        mock_create.side_effect = lambda h, a, p: ({
            "id": "a2a-inbound-1",
            "status": "working",
            "metadata": {"mailbus": {"taskId": "feat-ext-001", "stepId": "s1"}},
        }, 201, None)

        def fake_events(data_dir, wire_task, **kwargs):
            yield {"kind": "heartbeat"}
            yield {
                "kind": "update",
                "hub": {"status": "completed", "statusMessage": "done"},
                "final": True,
            }

        mock_iter.side_effect = fake_events
        handler = MockStreamingHandler(self.tmp, accept="text/event-stream")
        handler._body = {
            "jsonrpc": "2.0",
            "id": "rpc-hb",
            "method": "SendStreamingMessage",
            "params": {"message": {"parts": [{"text": "hb"}]}},
        }
        handle_a2a_rpc(handler, "lingzhao")
        raw = handler._wfile.getvalue().decode("utf-8")
        self.assertIn(": keepalive\n\n", raw)
        events = _parse_sse_jsonrpc_events(raw)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["result"]["status"]["state"], "completed")


if __name__ == "__main__":
    unittest.main()
