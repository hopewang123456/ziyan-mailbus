"""API 停滞检测与恢复。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.ops.api_stall_detect import detect_api_stall, api_stall_repush_wait_minutes
from lib.application.ops.api_stall_recovery import (
    repush_after_elapsed,
    schedule_api_stall_recovery,
    maybe_release_api_stall_for_repush,
)
from lib.adapters.ops.alerter import load_alerts
from lib.domain.models import Inbox, MsgStatus
from lib.infra.utils import json_write


class ApiStallDetectTests(unittest.TestCase):
    def test_detect_connection_refused(self):
        text = "Error: connect ECONNREFUSED 127.0.0.1:443"
        self.assertEqual(detect_api_stall(text), "api_network:econnrefused")

    def test_detect_codex_error_event(self):
        text = '{"type":"turn.failed","message":"fetch failed: network timeout"}'
        self.assertIsNotNone(detect_api_stall(text))

    def test_no_stall_on_normal_reply(self):
        self.assertIsNone(detect_api_stall("Step8 review passed, wrote step-s8.json"))


class ApiStallRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "inbox", "lingjian"), exist_ok=True)
        json_write(os.path.join(self.tmp, "config.json"), {
            "agents": {"lingjian": {"type": "codex"}, "lingzhao": {"type": "hermes"}},
            "pipeline_ops": {"api_stall": {"repush_wait_minutes": 3}},
        })
        inbox = {
            "agent": "lingjian",
            "has_unread": False,
            "messages": [{
                "id": "msg-test-1",
                "type": "task",
                "state": "processing",
                "status": "acknowledged",
                "content": "📋 【game-courier】pipeline",
                "pushed_count": 1,
            }],
        }
        json_write(os.path.join(self.tmp, "inbox", "lingjian", "inbox.json"), inbox)
        json_write(os.path.join(self.tmp, "replies", "lingjian.json"), {
            "msg_ids": ["msg-test-1"],
            "reply": "fetch failed: connection refused",
        })

    def test_schedule_sets_repush_after_and_alert(self):
        ok = schedule_api_stall_recovery(
            self.tmp, "lingjian", "msg-test-1",
            reason="api_network:econnrefused",
            task_id="game-courier",
        )
        self.assertTrue(ok)
        ib = Inbox.from_dict(
            __import__("lib.infra.utils", fromlist=["json_read"]).json_read(
                os.path.join(self.tmp, "inbox", "lingjian", "inbox.json"), {},
            )
        )
        m = ib.messages[0]
        self.assertTrue(ib.msg_field(m, "repush_after", ""))
        self.assertEqual(ib.msg_field(m, "api_stall_count", 0), 1)
        alerts = load_alerts(self.tmp)
        self.assertEqual(alerts["alerts"][-1]["type"], "api_unreachable")

    def test_repush_after_blocks_until_elapsed(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        self.assertFalse(repush_after_elapsed({"repush_after": future}))
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertTrue(repush_after_elapsed({"repush_after": past}))

    def test_maybe_release_after_cooldown(self):
        schedule_api_stall_recovery(
            self.tmp, "lingjian", "msg-test-1",
            reason="api_network:timeout", task_id="game-courier",
        )
        ib_path = os.path.join(self.tmp, "inbox", "lingjian", "inbox.json")
        ib = Inbox.from_dict(__import__("lib.infra.utils", fromlist=["json_read"]).json_read(ib_path, {}))
        m = ib.messages[0]
        if isinstance(m, dict):
            m["repush_after"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        json_write(ib_path, ib.to_dict())
        ib2 = Inbox.from_dict(__import__("lib.infra.utils", fromlist=["json_read"]).json_read(ib_path, {}))
        changed = maybe_release_api_stall_for_repush(
            self.tmp, "lingjian", ib2.messages[0], ib2, agents={"lingjian": {"type": "codex"}},
        )
        self.assertTrue(changed)
        ib3 = Inbox.from_dict(__import__("lib.infra.utils", fromlist=["json_read"]).json_read(ib_path, {}))
        self.assertEqual(ib3.msg_field(ib3.messages[0], "state", ""), MsgStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
