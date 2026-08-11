"""GET /api/harness-reports/<sha> 只读 API 单测。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.api.handlers_system import handle_harness_report
from lib.application.harness.report_api import (
    harness_report_path,
    harness_report_summary,
    load_harness_report,
    normalize_commit_sha,
)
from lib.infra.utils import json_write


class MockHandler:
    data_dir = ""
    _resp = None

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._resp = None

    def _send_json(self, data, status=200):
        self._resp = (data, status)


def _sample_report(sha: str) -> dict:
    return {
        "schema": "code-review-report-v1",
        "commit_sha": sha,
        "aggregate_status": "warn",
        "trigger": "post-commit-harness",
        "timestamp": "2026-06-30T12:00:00Z",
        "author_agent": "dali",
        "blocking": False,
        "layers": {
            "regression": {"status": "pass"},
            "static_analysis": {"status": "skip"},
            "ai_review": {"status": "warn", "summary": "minor style issues"},
        },
        "repo": {"name": "mail"},
    }


class TestHarnessReportApiHelpers(unittest.TestCase):
    def test_normalize_sha(self):
        self.assertEqual(normalize_commit_sha("abc1234"), "abc1234")
        self.assertEqual(normalize_commit_sha("abc1234.json"), "abc1234")
        self.assertIsNone(normalize_commit_sha("../evil"))
        self.assertIsNone(normalize_commit_sha("not-hex"))

    def test_load_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            sha = "a" * 40
            os.makedirs(os.path.join(tmp, "reports"), exist_ok=True)
            json_write(os.path.join(tmp, "reports", f"{sha}.json"), _sample_report(sha))
            doc = load_harness_report(tmp, sha)
            self.assertIsNotNone(doc)
            summary = harness_report_summary(doc)
            self.assertEqual(summary["aggregate_status"], "warn")
            self.assertEqual(summary["layers"]["regression"], "pass")
            self.assertIn("minor", summary["ai_review_summary"] or "")


class TestHarnessReportHandler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sha = "b" * 40
        os.makedirs(os.path.join(self.tmp, "reports"), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "reports", f"{self.sha}.json"),
            _sample_report(self.sha),
        )
        self.handler = MockHandler(self.tmp)

    def test_get_report_ok(self):
        handle_harness_report(self.handler, self.sha)
        data, status = self.handler._resp
        self.assertEqual(status, 200)
        self.assertEqual(data["commit_sha"], self.sha)
        self.assertEqual(data["summary"]["aggregate_status"], "warn")
        self.assertEqual(data["report"]["schema"], "code-review-report-v1")

    def test_invalid_sha_400(self):
        handle_harness_report(self.handler, "../../etc/passwd")
        _, status = self.handler._resp
        self.assertEqual(status, 400)

    def test_missing_report_404(self):
        handle_harness_report(self.handler, "c" * 40)
        data, status = self.handler._resp
        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "not_found")

    def test_path_traversal_blocked(self):
        path = harness_report_path(self.tmp, "../" + self.sha)
        self.assertIsNone(path)


if __name__ == "__main__":
    unittest.main()
