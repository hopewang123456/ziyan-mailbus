"""side-audit 与 primary pipeline 互斥。"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.orchestration.pipeline.task import (
    is_side_audit_message,
    side_audit_deferred_for_reviewer,
)
from lib.agent_adapters import CodexAdapter


class TestSideAuditDefer(unittest.TestCase):
    @patch("lib.pipeline_task.primary_pipeline_assignee", return_value="lingjian")
    def test_defer_when_primary_on_lingjian(self, *_):
        self.assertTrue(side_audit_deferred_for_reviewer("/tmp", "lingjian"))

    @patch("lib.pipeline_task.primary_pipeline_assignee", return_value="dali")
    def test_defer_when_any_primary_running(self, *_):
        """主 pipeline running 时 defer 全部 side-audit（Codex 单槽）。"""
        self.assertTrue(side_audit_deferred_for_reviewer("/tmp", "lingjian"))

    def test_is_side_audit_message(self):
        self.assertTrue(is_side_audit_message("audit-req-game-stellar-20260618"))
        self.assertFalse(is_side_audit_message("msg-20260625-70674"))

    def test_codex_cli_active_for_msg_id(self):
        adapter = CodexAdapter()
        ps_mixed = (
            "root 1 codex exec mailbus | agent=lingjian id=audit-req-x\n"
            "root 2 codex exec mailbus | agent=lingjian id=msg-20260625-70674\n"
        )
        self.assertTrue(
            adapter.cli_active_in_ps_for(
                "lingjian", {}, ps_mixed, msg_id="msg-20260625-70674",
            )
        )
        self.assertFalse(
            adapter.cli_active_in_ps_for(
                "lingjian", {}, ps_mixed, msg_id="msg-other",
            )
        )
        self.assertTrue(adapter.cli_active_in_ps("lingjian", {}, ps_mixed))


if __name__ == "__main__":
    unittest.main()
