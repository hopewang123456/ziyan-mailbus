"""Wave F3 HumanGate/Audit + F4 Notifier thick-cut tests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

from lib.adapters.orchestration.audit import FileAuditAdapter
from lib.adapters.orchestration.human_gate import HumanGateAdapter
from lib.adapters.orchestration.notifier import FileNotifier
from lib.composition import build_orchestration
from lib.application.harness.escalation import notify_verify_failure


class FakeNotifier:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def notify(self, event: str, payload: Mapping[str, Any] | None = None) -> None:
        self.events.append((event, dict(payload or {})))


class TestHumanGateAuditF3(unittest.TestCase):
    def test_enqueue_resolve_audit_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch = build_orchestration(tmp)
            self.assertIsNotNone(orch.human_gate)
            iid = orch.human_gate.enqueue({
                "type": "manual_note",
                "status": "pending",
                "title": "note for audit",
                "task_id": "t-f3-1",
            })
            self.assertTrue(iid.startswith("hq-"))
            out = orch.human_gate.resolve(
                iid,
                {"decision": "approved", "reviewer": "test", "comment": "ok"},
            )
            self.assertIsNotNone(out["item"])
            self.assertEqual(out["item"]["status"], "approved")

            audit_path = Path(tmp) / "system" / "audit.jsonl"
            self.assertTrue(audit_path.is_file())
            lines = [json.loads(x) for x in audit_path.read_text(encoding="utf-8").splitlines() if x.strip()]
            events = [row["event"] for row in lines]
            self.assertIn("human_gate.enqueue", events)
            self.assertIn("human_gate.resolve", events)

    def test_file_audit_env_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"MAILBUS_FILE_AUDIT": "0"}):
                orch = build_orchestration(tmp)
                orch.human_gate.enqueue({
                    "type": "plan_approval",
                    "status": "pending",
                    "title": "x",
                    "task_id": "t-off",
                })
            audit_path = Path(tmp) / "system" / "audit.jsonl"
            self.assertFalse(audit_path.is_file())

    def test_adapter_with_explicit_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = FileAuditAdapter(tmp)
            gate = HumanGateAdapter(tmp, audit=audit)
            iid = gate.enqueue({
                "type": "manual_note",
                "status": "pending",
                "title": "confirm",
                "task_id": "t-exp",
            })
            gate.resolve(iid, {"decision": "denied", "reviewer": "r", "reason": "no"})
            text = (Path(tmp) / "system" / "audit.jsonl").read_text(encoding="utf-8")
            self.assertIn("human_gate.enqueue", text)
            self.assertIn("human_gate.resolve", text)


class TestNotifierF4(unittest.TestCase):
    def test_file_notifier_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            n = FileNotifier(tmp)
            n.notify("demo_event", {"k": 1})
            path = Path(tmp) / "system" / "notifications.jsonl"
            self.assertTrue(path.is_file())
            row = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["event"], "demo_event")
            self.assertEqual(row["payload"]["k"], 1)

    def test_fake_notifier_records(self):
        fake = FakeNotifier()
        fake.notify("verify_fail_escalation", {"attempt": 3})
        self.assertEqual(fake.events[0][0], "verify_fail_escalation")
        self.assertEqual(fake.events[0][1]["attempt"], 3)

    def test_verify_escalation_calls_notifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inbox", "agent-a").mkdir(parents=True)
            Path(tmp, "config.json").write_text("{}", encoding="utf-8")
            notify_verify_failure(
                tmp,
                task_id="t-esc-3",
                agent="agent-i",
                role_label="实现",
                reason="missing_artifact",
                attempt=3,
                escalate_cfg={"2": "agent-m", "3": "agent-a"},
            )
            path = Path(tmp) / "system" / "notifications.jsonl"
            self.assertTrue(path.is_file())
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertTrue(any(r["event"] == "verify_fail_escalation" for r in rows))
            esc = next(r for r in rows if r["event"] == "verify_fail_escalation")
            self.assertEqual(esc["payload"]["escalate_to"], "agent-a")
            self.assertEqual(esc["payload"]["attempt"], 3)


if __name__ == "__main__":
    unittest.main()
