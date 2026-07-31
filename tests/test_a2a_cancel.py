"""A2A CancelTask / cancel_inflight / apply_cancel 单测。"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.handlers_a2a import handle_a2a_rpc
from lib.adapters.orchestration.task_fsm import TaskFsmState, apply_cancel, ensure_fsm
from lib.transport.a2a_cancel import cancel_inflight_a2a_for_task
from lib.transport.a2a_standard import A2ATransport
from lib.transport.types import DispatchContext
from lib.utils import json_read, json_write
from tests.test_helpers import seed_a2a_harness


class _CancelStubClient:
    def __init__(self):
        self.calls: list[str] = []

    def cancel_task(self, a2a_task_id: str) -> dict:
        self.calls.append(a2a_task_id)
        return {"ok": True, "id": a2a_task_id, "cancelled": True}


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


class TestCancelInflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _task_with_inflight(self) -> dict:
        return {
            "task_id": "cancel-feat-001",
            "status": "running",
            "fsm": {"state": TaskFsmState.EXECUTING.value, "history": []},
            "chain": [
                {
                    "step_id": "s1",
                    "fsm_state": "working",
                    "a2a_task_id": "a2a-remote-1",
                    "to_agent": "lingzhao",
                    "role_type": 1,
                },
                {
                    "step_id": "s2",
                    "fsm_state": "completed",
                    "status": "completed",
                    "a2a_task_id": "a2a-remote-2",
                    "to_agent": "lingzhao",
                    "role_type": 1,
                },
            ],
        }

    def test_cancel_inflight_calls_rpc_for_working_steps(self):
        task = self._task_with_inflight()
        stub = _CancelStubClient()
        transport = A2ATransport(rpc=stub)

        with patch("lib.transport.a2a_cancel.A2ATransport", return_value=transport):
            outcomes = cancel_inflight_a2a_for_task(self.tmp, task, reason="user_cancel")

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["a2a_task_id"], "a2a-remote-1")
        self.assertTrue(outcomes[0].get("ok"))
        self.assertEqual(stub.calls, ["a2a-remote-1"])

    def test_apply_cancel_invokes_cancel_inflight_and_sets_fsm(self):
        task = self._task_with_inflight()
        with patch("lib.transport.a2a_cancel.cancel_inflight_a2a_for_task") as mock_cancel:
            mock_cancel.return_value = [{"ok": True}]
            out = apply_cancel(task, reason="a2a_cancel", data_dir=self.tmp, agents={})
        mock_cancel.assert_called_once()
        self.assertTrue(out.get("ok"))
        ensure_fsm(task)
        self.assertEqual(task["fsm"]["state"], TaskFsmState.CANCELLED.value)
        self.assertEqual(task["status"], "cancelled")


class TestCancelTaskRpcHandler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        seed_a2a_harness(self.tmp)
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        self.tid = "cancel-rpc-001"
        self.task = {
            "task_id": self.tid,
            "status": "running",
            "fsm": {"state": TaskFsmState.EXECUTING.value, "history": []},
            "chain": [{
                "step_id": "s1",
                "fsm_state": "working",
                "a2a_task_id": "a2a-hub-task-99",
                "to_agent": "lingzhao",
                "role_type": 1,
            }],
        }
        json_write(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), self.task)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("lib.transport.a2a_cancel.cancel_inflight_a2a_for_task", return_value=[{"ok": True}])
    def test_rpc_cancel_task_by_mailbus_task_id(self, _mock_cancel):
        handler = MockRpcHandler(self.tmp)
        handler._body = {
            "jsonrpc": "2.0",
            "id": "rpc-cancel-1",
            "method": "CancelTask",
            "params": {"id": self.tid},
        }
        handle_a2a_rpc(handler, "lingzhao")
        self.assertIsNotNone(handler._resp_json)
        data, status = handler._resp_json
        self.assertEqual(status, 200)
        self.assertEqual(data["result"]["cancelled"], True)
        saved = json_read(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), {})
        self.assertEqual(saved["fsm"]["state"], TaskFsmState.CANCELLED.value)

    @patch("lib.transport.a2a_cancel.cancel_inflight_a2a_for_task", return_value=[{"ok": True}])
    def test_rpc_cancel_task_by_a2a_task_id(self, _mock_cancel):
        handler = MockRpcHandler(self.tmp)
        handler._body = {
            "jsonrpc": "2.0",
            "id": "rpc-cancel-2",
            "method": "CancelTask",
            "params": {"id": "a2a-hub-task-99"},
        }
        handle_a2a_rpc(handler, "lingzhao")
        data, status = handler._resp_json
        self.assertEqual(status, 200)
        self.assertTrue(data["result"]["cancelled"])

    def test_rpc_cancel_task_not_found(self):
        handler = MockRpcHandler(self.tmp)
        handler._body = {
            "jsonrpc": "2.0",
            "id": "rpc-cancel-3",
            "method": "CancelTask",
            "params": {"id": "missing-task"},
        }
        handle_a2a_rpc(handler, "lingzhao")
        data, status = handler._resp_json
        self.assertEqual(status, 404)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
