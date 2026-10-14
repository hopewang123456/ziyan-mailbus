"""P3 · tool_exec tool_live 开关。"""
import contextlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("fcntl", MagicMock())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.infra.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


_utils.file_lock = _noop_file_lock

from lib.infra.utils import json_write
from lib.application.workflow.tool_exec import mark_tool_live_after_gate, run_tool_step, tool_live_enabled


def _seed(tmp: str) -> None:
    from tests.test_helpers import seed_runtime_from_sot

    seed_runtime_from_sot(tmp, extra_config={
        "mailbus_workflow": {"tool_live": False, "tool_live_gates": ["publish_go"]},
    })


class TestToolLive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)
        self.task = {
            "task_id": "vid-tool-live",
            "intent": "发布测试",
            "extensions": {"mailbus": {"workflow": {"workflow_id": "video_publish", "gates": []}}},
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_dry_run(self):
        self.assertFalse(tool_live_enabled(self.tmp, self.task))

    def test_body_tool_live(self):
        self.assertTrue(tool_live_enabled(self.tmp, self.task, body={"tool_live": True}))

    def test_gate_def_on_approve_tool_live(self):
        gate_def = {"on_approve": {"action": "spawn_phase", "tool_live": True}}
        mark_tool_live_after_gate(self.task, {}, gate_def)
        self.assertTrue(self.task["extensions"]["mailbus"]["workflow"]["tool_live"])

    @patch("lib.application.workflow.tool_exec.get_integrations")
    def test_run_tool_step_respects_dry_run(self, mock_get):
        mock_port = MagicMock()
        mock_port.invoke_tool.return_value = {"ok": True, "dry_run": True}
        mock_get.return_value = mock_port
        run_tool_step(self.tmp, self.task, "webhook-multi-publish", dry_run=True)
        self.assertTrue(mock_port.invoke_tool.call_args.kwargs.get("dry_run"))

    @patch("lib.application.workflow.tool_exec.get_integrations")
    def test_run_tool_step_live(self, mock_get):
        mock_port = MagicMock()
        mock_port.invoke_tool.return_value = {"ok": True}
        mock_get.return_value = mock_port
        self.task["extensions"]["mailbus"]["workflow"]["tool_live"] = True
        run_tool_step(self.tmp, self.task, "webhook-multi-publish", dry_run=False)
        self.assertFalse(mock_port.invoke_tool.call_args.kwargs.get("dry_run"))


if __name__ == "__main__":
    unittest.main()
