"""Device Bridge 单元测试：配置段、token 绑定、通讯式一轮一答、ticket、隔离。"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.device_bridge import (
    DeviceBridgeError,
    deliver_and_wait,
    load_bridge_config,
    resolve_device,
    resolve_ticket,
)
from lib.adapters.config.config_admin import get_section, patch_section
from lib.infra.utils import json_write


def _minimal_config(devices=None, **bridge_overrides):
    cfg = {
        "project": "mailbus",
        "version": "1.0.0",
        "data_dir": ".",
        "ack_timeout": 30,
        "max_retries": 3,
        "archive_days": 3,
        "archive_max_messages": 300,
        "agents": {"lingzhao": {"type": "claude_code"}, "xiaoqi": {"type": "opencode"}},
        "mailbus_device_bridge": {
            "enabled": True,
            "default_wait_ms": 100,
            "write_memory": True,
            "devices": devices or [],
            **bridge_overrides,
        },
    }
    return cfg


class TestConfigSection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        json_write(
            os.path.join(self.tmp, "config.json"),
            _minimal_config(
                devices=[{"id": "phone-hope", "label": "希望的 iPhone",
                          "token_env": "MAILBUS_DEVICE_TOKEN_X", "tailscale_ips": ["100.1.2.3"],
                          "agent_id": "lingzhao", "enabled": True}],
            ),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_section_shape(self):
        out = get_section(self.tmp, "mailbus_device_bridge")
        self.assertEqual(out["section"], "mailbus_device_bridge")
        self.assertIn("enabled", out["data"])
        self.assertIn("devices", out["data"])
        self.assertIn("lingzhao", out["agents"])
        # token 不直接回传明文，仅回传是否配置
        dev = out["data"]["devices"][0]
        self.assertNotIn("token", dev)
        self.assertIn("token_configured", dev)

    def test_patch_section_replaces_devices(self):
        patch_section(self.tmp, "mailbus_device_bridge", {
            "default_wait_ms": 60000,
            "devices": [
                {"id": "phone-b", "label": "B", "token_env": "T_B", "agent_id": "xiaoqi", "enabled": True},
            ],
        })
        out = get_section(self.tmp, "mailbus_device_bridge")
        self.assertEqual(out["data"]["default_wait_ms"], 60000)
        self.assertEqual([d["id"] for d in out["data"]["devices"]], ["phone-b"])


class TestResolveDevice(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "enabled": True,
            "devices": [
                {"id": "a", "token_env": "T_A", "agent_id": "lingzhao", "enabled": True},
                {"id": "b", "token": "inline-b", "agent_id": "xiaoqi", "enabled": True,
                 "tailscale_ips": ["100.9.9.9"]},
                {"id": "c", "token_env": "T_C", "agent_id": "lingzhao", "enabled": False},
            ],
        }

    def test_env_token_match(self):
        with mock.patch.dict(os.environ, {"T_A": "secret-a"}):
            dev = resolve_device(self.cfg, "secret-a", "100.1.1.1")
            self.assertEqual(dev["id"], "a")

    def test_wrong_token(self):
        with mock.patch.dict(os.environ, {"T_A": "secret-a"}):
            self.assertIsNone(resolve_device(self.cfg, "nope", "100.1.1.1"))

    def test_inline_token(self):
        dev = resolve_device(self.cfg, "inline-b", "100.9.9.9")
        self.assertEqual(dev["id"], "b")

    def test_ip_whitelist_rejects(self):
        self.assertIsNone(resolve_device(self.cfg, "inline-b", "100.8.8.8"))

    def test_disabled_device_skipped(self):
        with mock.patch.dict(os.environ, {"T_C": "secret-c"}):
            self.assertIsNone(resolve_device(self.cfg, "secret-c", "100.1.1.1"))

    def test_bridge_disabled(self):
        cfg = {"enabled": False, "devices": self.cfg["devices"]}
        with mock.patch.dict(os.environ, {"T_A": "secret-a"}):
            self.assertIsNone(resolve_device(cfg, "secret-a", "100.1.1.1"))


class TestDeliverAndWait(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        json_write(os.path.join(self.tmp, "config.json"), _minimal_config())
        self.device = {"id": "phone-hope", "agent_id": "lingzhao", "enabled": True}
        self.agents = {"lingzhao": {"type": "claude_code"}, "xiaoqi": {"type": "opencode"}}
        self.agent_types = {}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unknown_agent(self):
        dev = {"id": "phone-hope", "agent_id": "ghost", "enabled": True}
        with self.assertRaises(DeviceBridgeError) as ctx:
            deliver_and_wait(self.tmp, self.agents, self.agent_types, dev, "hi", "s1", 100, {})
        self.assertEqual(ctx.exception.status, 404)

    def test_empty_text(self):
        with self.assertRaises(DeviceBridgeError):
            deliver_and_wait(self.tmp, self.agents, self.agent_types, self.device, "   ", "s1", 100, {})

    def test_ok_reply(self):
        with mock.patch(
            "lib.application.device_bridge._read_reply", return_value="pong",
        ), mock.patch("lib.application.device_bridge.record_device_memory"):
            result = deliver_and_wait(
                self.tmp, self.agents, self.agent_types, self.device, "ping", "s1", 1000, {},
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reply"], "pong")
        self.assertEqual(result["agent_id"], "lingzhao")
        self.assertEqual(result["session_id"], "s1")

    def test_pending_then_resolve(self):
        # 第一段：回复一直为空 → pending + ticket
        with mock.patch(
            "lib.application.device_bridge._read_reply", return_value="",
        ), mock.patch("lib.application.device_bridge.record_device_memory"):
            result = deliver_and_wait(
                self.tmp, self.agents, self.agent_types, self.device, "ping", "s1", 50, {},
            )
        self.assertEqual(result["status"], "pending")
        self.assertIn("ticket_id", result)
        self.assertIn("hint", result)

        # 第二段：回复到达 → 轮询 ok
        with mock.patch(
            "lib.application.device_bridge._read_reply", return_value="late-pong",
        ), mock.patch("lib.application.device_bridge.record_device_memory"):
            resolved = resolve_ticket(self.tmp, result["ticket_id"])
        self.assertEqual(resolved["status"], "ok")
        self.assertEqual(resolved["reply"], "late-pong")

    def test_stream_events_callback(self):
        events = []

        def on_event(name, data):
            events.append(name)

        with mock.patch(
            "lib.application.device_bridge._read_reply", return_value="pong",
        ), mock.patch("lib.application.device_bridge.record_device_memory"):
            result = deliver_and_wait(
                self.tmp, self.agents, self.agent_types, self.device, "ping", "s1", 1000, {},
                on_event=on_event,
            )
        self.assertEqual(result["status"], "ok")
        self.assertIn("accepted", events)
        self.assertIn("ok", events)

    def test_resolve_unknown_ticket(self):
        with self.assertRaises(DeviceBridgeError):
            resolve_ticket(self.tmp, "nope")

    def test_session_id_passthrough_and_isolation_from_task(self):
        # 投递的 inbox 消息应为 notice 型、from=device:<id>，且不含 task 字段（与工单流水线隔离）。
        # 注：device_session_id 属短会话元数据（用完即弃），push 归一化不持久化；轮次关联靠 msg_id。
        with mock.patch("lib.application.device_bridge._read_reply", return_value="pong"), \
                mock.patch("lib.application.device_bridge.record_device_memory"):
            result = deliver_and_wait(
                self.tmp, self.agents, self.agent_types, self.device, "ping", "sess-42", 1000, {},
            )

        self.assertEqual(result["session_id"], "sess-42")
        inbox_file = os.path.join(self.tmp, "inbox", "lingzhao", "inbox.json")
        from lib.infra.utils import json_read
        inbox = json_read(inbox_file, {})
        msgs = inbox.get("messages") or []
        self.assertTrue(msgs)
        last = msgs[-1]
        self.assertEqual(last["from"], "device:phone-hope")
        self.assertEqual(last["type"], "notice")
        self.assertNotIn("task", last)


if __name__ == "__main__":
    unittest.main()
