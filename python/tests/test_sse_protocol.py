"""SSE 协议层测试（PY4-A 双栈 SSE）— 协议一致性 + 签名漂移防护。

2026-10-27 实录 bug：``handlers_a2a`` 调 ``_send_sse_start(http_status=...)``，
而真实 ``MailbusAPIHandler._send_sse_start`` 签名无该关键字 → 真实服务器抛
``TypeError``；测试全绿是因为 mock 签名跟着写了 ``http_status``（与真实实现
漂移）。本文件用**真实 handler 类**做签名断言，把漂移钉死。
"""
from __future__ import annotations

import inspect
import json
import unittest

from lib.api.base import MailbusAPIHandler
from lib.api.sse import (
    MAX_ACTIVE_STREAMS,
    StreamLimitExceeded,
    acquire_stream_slot,
    active_stream_count,
    release_stream_slot,
    send_event,
)


class _FakeWFile:
    def __init__(self):
        self.buf = bytearray()

    def write(self, data: bytes) -> int:
        self.buf.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def getvalue(self) -> bytes:
        return bytes(self.buf)


class _FakeHandler:
    """最小 handler 替身（只需 wfile）。"""

    def __init__(self):
        self.wfile = _FakeWFile()


class TestSseSignatureConformance(unittest.TestCase):
    def test_real_handler_accepts_http_status_keyword(self):
        """真实 handler 必须接受 A2A 流式用的 http_status 关键字。"""
        sig = inspect.signature(MailbusAPIHandler._send_sse_start)
        self.assertIn("http_status", sig.parameters)
        self.assertEqual(
            sig.parameters["http_status"].kind,
            inspect.Parameter.KEYWORD_ONLY,
            "http_status 应为仅关键字参数",
        )

    def test_call_with_http_status_does_not_raise(self):
        """真调用一遍（用替身 wfile）——历史上这里会 TypeError。"""
        handler = _FakeHandler()
        sent = {}

        def send_response(status):
            sent["status"] = status

        handler.send_response = send_response
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None
        handler._apply_cors_headers = lambda: None
        MailbusAPIHandler._send_sse_start(handler, http_status=202)
        self.assertEqual(sent["status"], 202)

    def test_status_fallback_when_http_status_absent(self):
        handler = _FakeHandler()
        sent = {}
        handler.send_response = lambda status: sent.setdefault("status", status)
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None
        handler._apply_cors_headers = lambda: None
        MailbusAPIHandler._send_sse_start(handler, 200)
        self.assertEqual(sent["status"], 200)


class TestSseEventFormat(unittest.TestCase):
    def test_event_frame_shape(self):
        """帧格式：event: <name>\\ndata: <json>\\n\\n。"""
        handler = _FakeHandler()
        send_event(handler, "snapshot", {"a": 1})
        raw = handler.wfile.getvalue().decode("utf-8")
        self.assertTrue(raw.startswith("event: snapshot\n"))
        self.assertIn("\ndata: ", raw)
        self.assertTrue(raw.endswith("\n\n"))
        payload = raw.split("data: ", 1)[1].strip()
        self.assertEqual(json.loads(payload), {"a": 1})


class TestStreamConcurrencyGuard(unittest.TestCase):
    def test_limit_exceeded_raises(self):
        """并发流超上限抛 StreamLimitExceeded（调用方据此返 503）。"""
        try:
            for _ in range(MAX_ACTIVE_STREAMS):
                acquire_stream_slot()
            with self.assertRaises(StreamLimitExceeded):
                acquire_stream_slot()
        finally:
            for _ in range(MAX_ACTIVE_STREAMS + 1):
                release_stream_slot()

    def test_counter_returns_to_zero(self):
        acquire_stream_slot()
        release_stream_slot()
        self.assertEqual(active_stream_count(), 0)


if __name__ == "__main__":
    unittest.main()


class TestCollectCommandInboxPure(unittest.TestCase):
    """collect_command_inbox 必须是纯函数（SSE 抽取事故的回归钉子）。

    2026-10-28 冒烟实录：从 handle_command_inbox 抽出时体内残留
    ``handler.data_dir`` 引用 → SSE 首调 NameError（GET 面无测试覆盖，
    三件套全绿也没抓到）。本用例直接以纯函数形态调用，杜绝再犯。
    """

    def test_pure_function_no_handler_reference(self):
        import inspect
        from lib.api.handlers_tasks import collect_command_inbox
        src = inspect.getsource(collect_command_inbox)
        self.assertNotIn("handler.", src, "纯函数体内不得引用 handler")

    def test_returns_dict_shape(self):
        import tempfile, os
        from lib.api.handlers_tasks import collect_command_inbox
        with tempfile.TemporaryDirectory() as d:
            out = collect_command_inbox(d)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["identity"], {"id": "ziyan"})
        self.assertIn("items", out)
        self.assertIn("ziyan_inbox_unread", out)
