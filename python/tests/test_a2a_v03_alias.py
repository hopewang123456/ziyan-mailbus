"""M2d-b1：A2A 0.3 方法名 alias（message/send 等）与 0.2 名同响应。

双栈对等：java SDK 面（A2aSdkController）同样做双名归一。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.handlers_a2a import _A2A_METHOD_ALIASES, handle_a2a_rpc
from lib.infra.utils import json_write
from tests.test_helpers import seed_a2a_harness


class MockRpcHandler:
    data_dir = ""
    agents = {}
    headers: dict = {}

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.agents = {}
        self.headers = {}
        self._body = {}
        self._resp_json = None

    def _read_post_body(self):
        return self._body

    def _send_json(self, data, status=200):
        self._resp_json = (data, status)


class TestA2aMethodAliases(unittest.TestCase):
    def test_alias_table_covers_v03_methods(self):
        self.assertEqual(
            _A2A_METHOD_ALIASES,
            {
                "message/send": "SendMessage",
                "message/stream": "SendStreamingMessage",
                "tasks/get": "GetTask",
                "tasks/cancel": "CancelTask",
            },
        )

    def test_tasks_get_alias_hits_same_branch_as_0_2(self):
        tmp = tempfile.mkdtemp()
        try:
            seed_a2a_harness(tmp)
            os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
            task = {
                "task_id": "alias-get-001",
                "status": "running",
                "fsm": {"state": "executing", "history": []},
                "chain": [],
            }
            json_write(os.path.join(tmp, "tasks", "alias-get-001.json"), task)

            for method in ("GetTask", "tasks/get"):
                handler = MockRpcHandler(tmp)
                handler._body = {"jsonrpc": "2.0", "id": f"rpc-{method}",
                                 "method": method, "params": {"id": "alias-get-001"}}
                handle_a2a_rpc(handler, "agent-a")
                data, status = handler._resp_json
                self.assertEqual(status, 200, method)
                self.assertEqual(data["result"]["task"]["id"], "alias-get-001", method)
                # 富 wire（hubTask）：executing → working
                self.assertEqual(data["result"]["task"]["status"], "working", method)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_method_still_32601(self):
        tmp = tempfile.mkdtemp()
        try:
            seed_a2a_harness(tmp)
            handler = MockRpcHandler(tmp)
            handler._body = {"jsonrpc": "2.0", "id": 1, "method": "tasks/what", "params": {}}
            handle_a2a_rpc(handler, "agent-a")
            data, status = handler._resp_json
            self.assertEqual(status, 404)
            self.assertEqual(data["error"]["code"], -32601)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSdkWireStyle(unittest.TestCase):
    """M2d-b2b：SDK 面官方裸 Task 形状（java A2aSdkBridge.wireToSdkTask 同款）。"""

    def test_to_sdk_task_shape(self):
        from lib.api.handlers_a2a import _to_sdk_task
        out = _to_sdk_task({
            "id": "t1", "status": "input-required",
            "metadata": {"mailbus": {"taskId": "t1", "hqType": "plan_approval"}},
        })
        self.assertEqual(out["id"], "t1")
        self.assertEqual(out["contextId"], "t1")
        self.assertEqual(out["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
        self.assertIn("timestamp", out["status"])
        self.assertEqual(out["artifacts"], [])
        self.assertEqual(out["history"], [])
        self.assertEqual(out["metadata"]["mailbus"]["hqType"], "plan_approval")

    def test_sdk_style_rpc_returns_bare_task(self):
        tmp = tempfile.mkdtemp()
        try:
            seed_a2a_harness(tmp)
            os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
            task = {
                "task_id": "sdk-style-001", "status": "running",
                "fsm": {"state": "executing", "history": []}, "chain": [],
            }
            json_write(os.path.join(tmp, "tasks", "sdk-style-001.json"), task)
            from lib.api.handlers_a2a import handle_a2a_sdk_rpc
            handler = MockRpcHandler(tmp)
            handler._body = {"jsonrpc": "2.0", "id": 1, "method": "tasks/get",
                             "params": {"id": "sdk-style-001"}}
            handle_a2a_sdk_rpc(handler, "agent-a")
            data, status = handler._resp_json
            self.assertEqual(status, 200)
            result = data["result"]
            self.assertNotIn("task", result)  # 官方裸形状：无 task 包装
            self.assertEqual(result["id"], "sdk-style-001")
            self.assertEqual(result["status"]["state"], "TASK_STATE_WORKING")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSdkStreamFrames(unittest.TestCase):
    """M2d-b2b：SDK 面流式帧=TaskStatusUpdateEvent 形状（无 final，java statusEvent 同款）。"""

    def test_sdk_stream_frames_shape(self):
        from unittest.mock import patch
        from lib.api import handlers_a2a

        class SseHandler(MockRpcHandler):
            def __init__(self, data_dir):
                super().__init__(data_dir)
                self.frames = []

            def _send_sse_start(self, **kwargs):
                pass

            def _send_sse_jsonrpc(self, rpc_id, payload):
                self.frames.append(payload)

            def _send_sse_comment(self):
                pass

        events = [
            {"kind": "update", "hub": {"id": "t9", "status": "input-required",
                                       "metadata": {"mailbus": {"taskId": "t9"}}}, "final": False},
            {"kind": "update", "hub": {"id": "t9", "status": "canceled",
                                       "metadata": {"mailbus": {"taskId": "t9"}}}, "final": True},
        ]
        handler = SseHandler("")
        with patch("lib.core.a2a.a2a_stream.iter_stream_events", return_value=iter(events)):
            handlers_a2a._stream_a2a_task_progress(handler, "rpc-1", {"id": "t9"}, wire_style="sdk")
        self.assertEqual(len(handler.frames), 2)
        for frame in handler.frames:
            self.assertEqual(frame["taskId"], "t9")
            self.assertEqual(frame["contextId"], "t9")
            self.assertIn("state", frame["status"])
            self.assertNotIn("final", frame)  # SDK 形状无 final（流结束=连接关闭）
        self.assertEqual(handler.frames[0]["status"]["state"], "TASK_STATE_INPUT_REQUIRED")
        self.assertEqual(handler.frames[1]["status"]["state"], "TASK_STATE_CANCELED")

        # legacy 回归：0.2 帧保持 build_status_update_result（含 final、kebab state）
        handler2 = SseHandler("")
        with patch("lib.core.a2a.a2a_stream.iter_stream_events", return_value=iter(events)):
            handlers_a2a._stream_a2a_task_progress(handler2, "rpc-1", {"id": "t9"})
        self.assertEqual(handler2.frames[0]["status"]["state"], "input-required")
        self.assertTrue(handler2.frames[1]["final"])


if __name__ == "__main__":
    unittest.main()
