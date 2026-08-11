"""ProductionHarness wait/poll 与 scanner/pusher 产物协作。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.harness import get_harness
from lib.application.orchestration.pipeline.results import step_result_path
from lib.core.a2a.dispatch_integration import dispatch_pipeline_step
from lib.core.a2a.file_bus import FileBusTransport
from lib.core.a2a.step_result_io import read_step_result_file, write_step_result_file
from lib.core.a2a.types import DispatchContext
from lib.infra.utils import json_write, resolve_paths
from tests.test_helpers import seed_a2a_harness


class TestProductionHarnessWait(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("harness", {})["mode"] = "production"
        cfg.setdefault("agents", {})["dali"] = {
            "type": "opencode",
            "channels": {"a2a": {"enabled": False}, "file_bus": {"enabled": True}},
        }
        json_write(cfg_path, cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _spawn(self, task_id: str = "feat-auth-001", step_id: str = "s3"):
        harness = get_harness({"harness": {"mode": "production"}})
        session = harness.spawn(
            "dali",
            {
                "data_dir": self.tmp,
                "task_id": task_id,
                "step_id": step_id,
            },
        )
        return harness, session

    def test_wait_finds_existing_step_result(self):
        harness, session = self._spawn()
        write_step_result_file(
            self.tmp, "feat-auth-001", "s3",
            {"conclusion": "done", "agent": "dali", "summary": "ok"},
        )
        outcome = harness.wait_completion(session, timeout=5)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.step_result.get("conclusion"), "done")

    def test_wait_polls_until_step_result_appears(self):
        harness, session = self._spawn("poll-task", "s1")

        def _write_later():
            time.sleep(0.3)
            write_step_result_file(
                self.tmp, "poll-task", "s1",
                {"conclusion": "done", "agent": "dali"},
            )

        threading.Thread(target=_write_later, daemon=True).start()
        outcome = harness.wait_completion(session, timeout=10)
        self.assertTrue(outcome.ok)

    def test_wait_records_ack_from_pusher_path(self):
        harness, session = self._spawn()
        paths = resolve_paths(self.tmp)
        ack_dir = os.path.join(paths["inbox"], "dali")
        os.makedirs(ack_dir, exist_ok=True)
        json_write(
            os.path.join(ack_dir, "ack.json"),
            [{"action": "ack", "msg_id": session.msg_id}],
        )
        write_step_result_file(
            self.tmp, "feat-auth-001", "s3",
            {"conclusion": "done", "agent": "dali"},
        )
        outcome = harness.wait_completion(session, timeout=5)
        self.assertTrue(outcome.ok)
        self.assertTrue(outcome.ack_received)

    def test_wait_timeout_without_result(self):
        harness, session = self._spawn("no-result", "s9")
        outcome = harness.wait_completion(session, timeout=2)
        self.assertFalse(outcome.ok)
        self.assertIn("timeout", outcome.error or "")


class TestFileBusProductionWait(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp, mode="production")
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("harness", {})["mode"] = "production"
        cfg.setdefault("harness", {}).setdefault("file_bus", {})["ack_timeout_sec"] = 3
        cfg.setdefault("transport", {})["use_router"] = True
        cfg.setdefault("agents", {})["dali"] = {
            "type": "opencode",
            "channels": {"a2a": {"enabled": False}, "file_bus": {"enabled": True}},
        }
        json_write(cfg_path, cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _transport(self) -> FileBusTransport:
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return FileBusTransport(harness=get_harness(cfg), mode="production")

    def test_production_dispatch_waits_for_delayed_step_result(self):
        transport = self._transport()
        ctx = DispatchContext(self.tmp, "wait-task", "s2", "dali", 8, intent="run step")

        def _write_later():
            time.sleep(0.5)
            write_step_result_file(
                self.tmp, "wait-task", "s2",
                {"conclusion": "done", "agent": "dali", "summary": "ok"},
            )

        threading.Thread(target=_write_later, daemon=True).start()
        result = transport.dispatch(ctx, {"dali": {"type": "opencode"}})
        self.assertTrue(result.ok)
        self.assertTrue(result.step_result_path)
        self.assertTrue(os.path.isfile(result.step_result_path))
        sr = read_step_result_file(self.tmp, "wait-task", "s2")
        self.assertEqual(sr.get("conclusion"), "done")

    def test_production_dispatch_writes_inbox_before_wait(self):
        transport = self._transport()
        write_step_result_file(
            self.tmp, "inbox-task", "s1",
            {"conclusion": "done", "agent": "dali"},
        )
        ctx = DispatchContext(self.tmp, "inbox-task", "s1", "dali", 8)
        transport.dispatch(ctx, {"dali": {"type": "opencode"}})
        inbox_path = os.path.join(self.tmp, "inbox", "dali", "inbox.json")
        with open(inbox_path, encoding="utf-8") as f:
            inbox = json.load(f)
        ids = [m.get("id") for m in inbox.get("messages") or []]
        self.assertIn("msg-inbox-task-s1", ids)

    def test_production_dispatch_timeout_audit(self):
        transport = self._transport()
        ctx = DispatchContext(self.tmp, "timeout-task", "s9", "dali", 8)
        result = transport.dispatch(ctx, {"dali": {"type": "opencode"}})
        self.assertFalse(result.ok)
        self.assertTrue(result.error.startswith("retryable:"))
        err_dir = os.path.join(self.tmp, "errors")
        self.assertTrue(any(f.startswith("file-bus-wait-") for f in os.listdir(err_dir)))

    def test_dispatch_integration_production_wait(self):
        write_step_result_file(
            self.tmp, "pipe-task", "s1",
            {"conclusion": "done", "agent": "dali"},
        )
        out = dispatch_pipeline_step(
            self.tmp,
            task_id="pipe-task",
            step_id="s1",
            to_agent="dali",
            role_type=8,
            intent="pipeline step",
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("transport_used"), "file_bus")
        self.assertTrue(out.get("step_result_path"))


if __name__ == "__main__":
    unittest.main()
