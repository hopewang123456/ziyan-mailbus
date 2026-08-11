"""AgentHarness.reconcile 薄包装测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.harness import AgentHarness, get_harness
from lib.infra.utils import json_write


class TestHarnessReconcile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        json_write(os.path.join(self.tmp, "config.json"), {"agents": {"lingzhao": {}}})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("lib.application.orchestration.execution.run_orchestrator")
    def test_reconcile_delegates_to_orchestrator(self, mock_run):
        mock_run.return_value = {
            "anomalies": [{"kind": "test-anomaly"}],
            "reconcile": {"cancelled_tasks": 0},
            "anomaly_count": 1,
        }
        harness = AgentHarness()
        out = harness.reconcile(self.tmp)
        self.assertEqual(out, [{"kind": "test-anomaly"}])
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], self.tmp)
        self.assertEqual(args[1], {"lingzhao": {}})
        self.assertTrue(kwargs.get("fix"))
        self.assertEqual(kwargs.get("mode"), "light")

    def test_stub_harness_inherits_reconcile(self):
        harness = get_harness({"harness": {"mode": "stub"}})
        out = harness.reconcile(self.tmp)
        self.assertIsInstance(out, list)


if __name__ == "__main__":
    unittest.main()
