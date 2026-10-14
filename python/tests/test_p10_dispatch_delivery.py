"""P10: claude_code/local_cli assignee dispatch — delivery semantics + honest failure.

Root cause fixed here:
- core file_bus production spawn sent only the contract summary (how to reply),
  never the work-order intent (what to do);
- dispatch blocked synchronously up to ack_timeout (300s) waiting for a
  step-result that local push CLIs were never told how/where to write;
- cmd_task_from_template printed ✓ regardless of dispatch outcome.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.a2a.dispatch_integration import dispatch_pipeline_step
from lib.core.a2a.file_bus import FileBusTransport
from lib.core.a2a.types import DispatchContext
from tests.test_helpers import seed_a2a_harness


class _FakeHarness:
    """Captures spawn payloads; never waits."""

    def __init__(self):
        self.spawned: list[dict] = []

    def spawn(self, agent_id: str, payload: dict):
        self.spawned.append({"agent_id": agent_id, **payload})
        return mock.Mock()

    def wait_completion(self, session, timeout: int = 300):
        raise AssertionError("dispatch must not wait when wait_on_dispatch is off")


class _LocalCliStore(unittest.TestCase):
    """Store with one local_cli agent (claude_code) — mirrors P10 repro."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp, mode="production")
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["harness"]["mode"] = "production"
        cfg.setdefault("transport", {})["use_router"] = True
        cfg.setdefault("agents", {})["agent-c"] = {
            "type": "claude_code",
            "transport": "local_cli",
            "channels": {"a2a": {"enabled": False}, "file_bus": {"enabled": True}},
        }
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestFileBusDeliverySemantics(_LocalCliStore):
    def test_dispatch_returns_fast_with_inbox_and_prompt(self):
        harness = _FakeHarness()
        transport = FileBusTransport(harness=harness, mode="production")
        ctx = DispatchContext(
            self.tmp, "p10-task", "s1", "agent-c", 8,
            intent="整理目录并输出清单",
        )

        t0 = time.monotonic()
        result = transport.dispatch(ctx, {"agent-c": {"type": "claude_code"}})
        elapsed = time.monotonic() - t0

        self.assertTrue(result.ok)
        self.assertLess(elapsed, 5, "dispatch must not block on ack_timeout")
        inbox_path = os.path.join(self.tmp, "inbox", "agent-c", "inbox.json")
        with open(inbox_path, encoding="utf-8") as f:
            inbox = json.load(f)
        msg = next(
            m for m in inbox["messages"] if m["id"] == "msg-p10-task-s1"
        )
        self.assertEqual(msg["content"], "整理目录并输出清单")
        # P10 core: the spawned CLI must receive the work order, not just the contract
        self.assertEqual(len(harness.spawned), 1)
        self.assertIn("整理目录并输出清单", harness.spawned[0]["prompt"])

    def test_wait_on_dispatch_opt_in_still_waits(self):
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("harness", {}).setdefault("file_bus", {})["wait_on_dispatch"] = True
        cfg["harness"]["file_bus"]["ack_timeout_sec"] = 1
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        harness = _FakeHarness()

        class _Outcome:
            ok = False
            step_result = None
            error = "timeout waiting for step-result"
            ack_received = False

        harness.wait_completion = mock.Mock(return_value=_Outcome())
        transport = FileBusTransport(harness=harness, mode="production")
        ctx = DispatchContext(self.tmp, "w-task", "s1", "agent-c", 8, intent="x")
        result = transport.dispatch(ctx, {"agent-c": {"type": "claude_code"}})
        self.assertFalse(result.ok)
        self.assertTrue(result.error and result.error.startswith("retryable:"))
        harness.wait_completion.assert_called_once()


class TestMessagePortNotifyDefault(_LocalCliStore):
    def test_dispatch_via_message_port_notifies_without_wait(self):
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["transport"]["use_message_port"] = True
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        fake = _FakeHarness()
        with mock.patch("lib.application.harness.get_harness", return_value=fake):
            out = dispatch_pipeline_step(
                self.tmp,
                task_id="mp-task",
                step_id="s1",
                to_agent="agent-c",
                role_type=8,
                intent="mp 工单",
            )
        self.assertTrue(out.get("ok"), msg=str(out))
        self.assertEqual(out.get("via"), "message_transport_port")
        inbox_path = os.path.join(self.tmp, "inbox", "agent-c", "inbox.json")
        with open(inbox_path, encoding="utf-8") as f:
            inbox = json.load(f)
        self.assertTrue(any(m["id"] == "msg-mp-task-s1" for m in inbox["messages"]))
        self.assertEqual(len(fake.spawned), 1)
        self.assertIn("mp 工单", fake.spawned[0]["prompt"])


class TestRouterPathFastDelivery(_LocalCliStore):
    def test_router_dispatch_local_cli_returns_ok_quickly(self):
        """End-to-end through TransportRouter (use_router=true) — no 300s block."""
        fake = _FakeHarness()
        with mock.patch("lib.composition.get_harness", return_value=fake):
            out = dispatch_pipeline_step(
                self.tmp,
                task_id="rt-task",
                step_id="s1",
                to_agent="agent-c",
                role_type=8,
                intent="router 工单",
            )
        self.assertTrue(out.get("ok"), msg=str(out))
        self.assertEqual(out.get("transport_used"), "file_bus")
        self.assertEqual(len(fake.spawned), 1)


class TestFirstStepFailureHonesty(unittest.TestCase):
    def test_dispatch_failure_marks_task_blocked(self):
        from lib.application.orchestration.router import dispatch as router_dispatch

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        seed_a2a_harness(tmp, mode="production")
        task = {
            "task_id": "blk-1",
            "status": "running",
            "chain": [
                {"step": 1, "step_id": "s1", "role_type": 8,
                 "to_agent": "agent-x", "to_person": "agent-x",
                 "fsm_state": "queued", "status": "running"}
            ],
        }
        os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
        with open(os.path.join(tmp, "tasks", "blk-1.json"), "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False)

        with mock.patch.object(router_dispatch, "dispatch_fsm_step", return_value=False):
            ok = router_dispatch.dispatch_first_step(tmp, task)

        self.assertFalse(ok)
        with open(os.path.join(tmp, "tasks", "blk-1.json"), encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["status"], "blocked")
        self.assertEqual(on_disk["fsm"]["state"], "blocked")
        self.assertEqual(on_disk["fsm"]["reason"], "first_step_dispatch_failed")


if __name__ == "__main__":
    unittest.main()
