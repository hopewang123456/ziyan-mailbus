"""a2a_poll：input-required 超时扫描 + pending GetTask 轮询。"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.orchestration.a2a_poll import check_input_required_timeouts, poll_pending_a2a_tasks
from lib.adapters.orchestration.human_queue import enqueue
from lib.application.orchestration.tracker import TaskTracker
from lib.core.a2a.step_result_io import read_step_result_file
from lib.infra.utils import _now_iso, json_write
from tests.test_helpers import seed_a2a_harness


def _lingzhao_agent() -> dict:
    return {
        "type": "hermes_profile",
        "role_types": [1],
        "channels": {"a2a": {"enabled": True}, "file_bus": {"enabled": True}},
        "endpoint": {"base_url": "https://mailbus.example/api/a2a/rpc/lingzhao"},
        "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
    }


class TestInputRequiredTimeout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(
            self.tmp,
            extra_config={
                "transport": {
                    "use_router": True,
                    "a2a": {"input_required_timeout_sec": 3600},
                },
            },
        )
        os.makedirs(os.path.join(self.tmp, "inbox", "lingxun"), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "inbox", "lingxun", "inbox.json"),
            {"agent": "lingxun", "messages": []},
        )
        json_write(
            os.path.join(self.tmp, "tasks", "feat-timeout-001.json"),
            {
                "task_id": "feat-timeout-001",
                "status": "running",
                "fsm": {"state": "executing"},
                "chain": [],
            },
        )
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%S+0000")
        enqueue(self.tmp, {
            "id": "hq-timeout-test",
            "type": "a2a_input_required",
            "status": "pending",
            "title": "需确认",
            "task_id": "feat-timeout-001",
            "created_at": old,
            "context": {"step_id": "s1", "prompt": "JWT?"},
        })
        self.paths = {"inbox": os.path.join(self.tmp, "inbox")}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_timeout_blocks_task_and_logs(self):
        n = check_input_required_timeouts(self.tmp, {}, self.paths)
        self.assertEqual(n, 1)
        task = TaskTracker(self.tmp).get("feat-timeout-001")
        self.assertEqual(task["fsm"]["state"], "blocked")
        self.assertIn("input_required_timeout", task.get("error", ""))

        logs = glob.glob(os.path.join(self.tmp, "errors", "a2a-fallback-*.jsonl"))
        self.assertTrue(logs)
        lines = open(logs[0], encoding="utf-8").read().strip().splitlines()
        evt = json.loads(lines[-1])
        self.assertEqual(evt["event"], "input_required_timeout")
        self.assertEqual(evt["task_id"], "feat-timeout-001")
        self.assertEqual(evt["hq_id"], "hq-timeout-test")

    def test_fresh_item_not_timed_out(self):
        """仅含未超时的 HQ 项时不应 block。"""
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(
            self.tmp,
            extra_config={
                "transport": {
                    "use_router": True,
                    "a2a": {"input_required_timeout_sec": 3600},
                },
            },
        )
        json_write(
            os.path.join(self.tmp, "tasks", "feat-fresh-001.json"),
            {"task_id": "feat-fresh-001", "status": "running", "fsm": {"state": "executing"}, "chain": []},
        )
        enqueue(self.tmp, {
            "id": "hq-fresh",
            "type": "final_acceptance",
            "status": "pending",
            "title": "终验",
            "task_id": "feat-fresh-001",
            "created_at": _now_iso(),
        })
        n = check_input_required_timeouts(self.tmp, {}, {"inbox": os.path.join(self.tmp, "inbox")})
        self.assertEqual(n, 0)
        task = TaskTracker(self.tmp).get("feat-fresh-001")
        self.assertEqual(task["fsm"]["state"], "executing")


class TestPollPendingA2A(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(
            self.tmp,
            extra_config={"transport": {"use_router": True}},
        )
        cfg_path = os.path.join(self.tmp, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("agents", {})["lingzhao"] = _lingzhao_agent()
        json_write(cfg_path, cfg)
        json_write(
            os.path.join(self.tmp, "tasks", "feat-poll-001.json"),
            {
                "task_id": "feat-poll-001",
                "status": "running",
                "fsm": {"state": "executing"},
                "chain": [{
                    "step_id": "s1",
                    "to_agent": "lingzhao",
                    "to_person": "lingzhao",
                    "role_type": 1,
                    "a2a_task_id": "a2a-7f3c-9e2a-4b1d-8c6f-2a1e9d4f0b3c",
                    "transport_used": "a2a_standard",
                    "status": "running",
                    "started_at": _now_iso(),
                }],
            },
        )
        self.paths = {"inbox": os.path.join(self.tmp, "inbox")}
        self.agents = json.load(open(cfg_path, encoding="utf-8"))["agents"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("lib.application.orchestration.pipeline.trigger.trigger")
    def test_poll_pending_get_task_writes_step_result(self, mock_trigger):
        """poll_pending_a2a_tasks：stub GetTask 完成后写入 step-result。"""
        n = poll_pending_a2a_tasks(self.tmp, self.agents, self.paths)
        self.assertEqual(n, 1)
        mock_trigger.assert_called_once()
        sr = read_step_result_file(self.tmp, "feat-poll-001", "s1")
        self.assertIsNotNone(sr)
        self.assertEqual(sr.get("conclusion"), "done")
        self.assertEqual(sr.get("agent"), "lingzhao")
        self.assertEqual(sr.get("transport_used"), "a2a_standard")


if __name__ == "__main__":
    unittest.main()
