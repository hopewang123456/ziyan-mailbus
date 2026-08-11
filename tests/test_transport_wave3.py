"""Wave3 MessageTransportPort + locale coverage."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.adapters.transport.file_bus import FileBusMessageTransport
from lib.adapters.transport.router import SelectingMessageTransport, resolve_channel
from lib.domain.error_codes import ALL_STABLE_CODES, ALL_TRANSPORT_CODES
from lib.domain.types import OutboundMessage
from lib.adapters.locale.errors_zh import ERROR_ZH, message_zh, stable_codes_covered, transport_codes_covered


class TestLocaleTransport(unittest.TestCase):
    def test_all_codes_have_zh(self):
        self.assertTrue(transport_codes_covered())
        self.assertTrue(stable_codes_covered())
        for c in ALL_TRANSPORT_CODES:
            self.assertIn(c, ERROR_ZH)
        for c in ALL_STABLE_CODES:
            self.assertIn(c, ERROR_ZH)
            self.assertTrue(message_zh(c))


class TestFileBusPort(unittest.TestCase):
    def test_send_writes_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = OutboundMessage(
                agent_id="lingzhao",
                msg_id="msg-t1-s1",
                body_path="",
                headers={"data_dir": tmp, "intent": "hello", "task_id": "t1", "step_id": "s1"},
            )
            r = FileBusMessageTransport().send(msg)
            self.assertTrue(r.accepted)
            self.assertEqual(r.channel, "file_bus")
            inbox = json.loads(Path(tmp, "inbox", "lingzhao", "inbox.json").read_text(encoding="utf-8"))
            self.assertEqual(inbox["messages"][0]["id"], "msg-t1-s1")


class TestResolveChannel(unittest.TestCase):
    def test_force_a2a(self):
        self.assertEqual(resolve_channel("a", {"channel": "http_a2a"}, {}), "http_a2a")

    def test_webhook_preferred(self):
        cfg = {"agents": {"x": {"webhook_url": "http://x", "channels": {"preferred": "webhook"}}}}
        self.assertEqual(resolve_channel("x", {}, cfg), "webhook")

    def test_default_file_bus(self):
        self.assertEqual(resolve_channel("z", {}, {"agents": {}}), "file_bus")


class TestSelectingFallback(unittest.TestCase):
    def test_a2a_fail_falls_back_file_bus(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.json").write_text("{}", encoding="utf-8")
            sel = SelectingMessageTransport(tmp, {})
            msg = OutboundMessage(
                agent_id="a",
                msg_id="m1",
                body_path="",
                headers={"data_dir": tmp, "channel": "http_a2a", "intent": "x", "task_id": "t", "step_id": "s"},
            )

            class Boom:
                def send(self, _m):
                    from lib.domain.types import TransportReceipt

                    return TransportReceipt(
                        msg_id="m1", accepted=False, detail="down", channel="http_a2a", error_code="transport_a2a"
                    )

            with patch.object(sel, "_a2a", Boom()):
                r = sel.send(msg)
            self.assertTrue(r.accepted)
            self.assertEqual(r.channel, "file_bus")


class TestSendOutbound(unittest.TestCase):
    def test_application_send(self):
        from lib.application.transport_send import send_outbound

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.json").write_text("{}", encoding="utf-8")
            out = send_outbound(tmp, agent_id="b", msg_id="m2", intent="hi", channel="file_bus")
            self.assertTrue(out["ok"])
            self.assertEqual(out["channel"], "file_bus")


class TestFileBusWaitPort(unittest.TestCase):
    """W7c: MessageTransportPort file_bus + Harness wait."""

    def test_wait_with_prewritten_step_result(self):
        from lib.adapters.transport.file_bus import FileBusMessageTransport
        from lib.core.a2a.step_result_io import write_step_result_file

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.json").write_text(
                json.dumps({"harness": {"mode": "production"}}),
                encoding="utf-8",
            )
            write_step_result_file(
                tmp, "t-w7c", "s1",
                {"conclusion": "done", "agent": "agent-a", "summary": "ok"},
            )
            msg = OutboundMessage(
                agent_id="agent-a",
                msg_id="msg-t-w7c-s1",
                body_path="",
                headers={
                    "data_dir": tmp,
                    "intent": "do it",
                    "task_id": "t-w7c",
                    "step_id": "s1",
                    "wait": "1",
                    "allow_no_spawn": "1",
                    "wait_timeout_sec": "5",
                },
            )
            r = FileBusMessageTransport().send(msg)
            self.assertTrue(r.accepted, msg=r.detail)
            self.assertEqual(r.channel, "file_bus")
            self.assertIn("step_result", r.detail)
            inbox = json.loads(Path(tmp, "inbox", "agent-a", "inbox.json").read_text(encoding="utf-8"))
            self.assertEqual(inbox["messages"][0]["id"], "msg-t-w7c-s1")

    def test_dispatch_via_message_port_flag(self):
        from lib.core.a2a.dispatch_integration import dispatch_pipeline_step
        from lib.core.a2a.step_result_io import write_step_result_file

        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "transport": {"use_router": True, "use_message_port": True},
                "harness": {"mode": "production"},
                "agents": {"agent-a": {"type": "opencode"}},
            }
            Path(tmp, "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            write_step_result_file(
                tmp, "t2", "s2",
                {"conclusion": "done", "agent": "agent-a", "summary": "ok"},
            )
            out = dispatch_pipeline_step(
                tmp,
                task_id="t2",
                step_id="s2",
                to_agent="agent-a",
                role_type=8,
                intent="hi",
                config=cfg,
            )
            self.assertTrue(out.get("ok"), msg=str(out))
            self.assertEqual(out.get("via"), "message_transport_port")
            self.assertEqual(out.get("transport_used"), "file_bus")


class TestTransportErrorDomain(unittest.TestCase):
    def test_retryable_to_domain(self):
        from lib.core.a2a.errors import RetryableTransportError

        e = RetryableTransportError("timeout", code="504")
        d = e.to_domain()
        self.assertEqual(d.code, "504")


if __name__ == "__main__":
    unittest.main()
