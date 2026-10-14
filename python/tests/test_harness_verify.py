"""Quality Harness 报告 sha 校验测试。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.ops.verify.harness_report import verify_harness_report
from lib.application.ops.verify.runner import run_step_verify
from lib.application.ops.verify.step_verify import verify_review_done
from lib.application.orchestration.router.planner import plan_tier0


class TestHarnessReportVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sha = "a" * 40
        os.makedirs(os.path.join(self.tmp, "reports"), exist_ok=True)
        self.report_path = os.path.join(self.tmp, "reports", f"{self.sha}.json")
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump({
                "schema": "code-review-report-v1",
                "commit_sha": self.sha,
                "aggregate_status": "warn",
                "layers": {},
                "timestamp": "2026-06-30T00:00:00Z",
            }, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_approve_requires_matching_report(self):
        result = {
            "conclusion": "pass",
            "attachments": [{"kind": "report", "ref": f"store/reports/{self.sha}.json"}],
            "extensions": {"harness_verdict": "APPROVE", "commit_sha": self.sha},
        }
        ok, err, meta = verify_harness_report(result, self.tmp, strict=False)
        self.assertTrue(ok, err)
        self.assertEqual(meta.get("report_aggregate_status"), "warn")

    def test_report_with_static_analysis_layer(self):
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump({
                "schema": "code-review-report-v1",
                "commit_sha": self.sha,
                "aggregate_status": "pass",
                "layers": {
                    "static_analysis": {
                        "status": "pass",
                        "tools": {"pylint": {"status": "pass", "score": 10.0}},
                    },
                },
                "timestamp": "2026-06-30T00:00:00Z",
            }, f)
        result = {
            "attachments": [{"kind": "report", "ref": f"store/reports/{self.sha}.json"}],
            "extensions": {"harness_verdict": "APPROVE", "commit_sha": self.sha},
        }
        ok, err, meta = verify_harness_report(result, self.tmp, strict=False)
        self.assertTrue(ok, err)
        self.assertEqual(meta.get("report_aggregate_status"), "pass")

    def test_sha_mismatch_fails(self):
        result = {
            "attachments": [{"kind": "report", "ref": f"store/reports/{self.sha}.json"}],
            "extensions": {
                "harness_verdict": "APPROVE",
                "commit_sha": "b" * 40,
            },
        }
        ok, err, _ = verify_harness_report(result, self.tmp, strict=False)
        self.assertFalse(ok)
        self.assertIn("mismatch", err or "")

    def test_missing_report_fails_on_approve(self):
        result = {
            "extensions": {"harness_verdict": "APPROVE", "commit_sha": "c" * 40},
        }
        ok, err, _ = verify_harness_report(result, self.tmp, strict=False)
        self.assertFalse(ok)
        self.assertIn("missing", err or "")

    def test_reject_verdict_in_step_verify(self):
        ok, err = verify_review_done({"harness_verdict": "REJECT"}, strict=False)
        self.assertFalse(ok)
        self.assertIn("REJECT", err or "")

    def test_runner_integrates_harness_check(self):
        result = {
            "conclusion": "pass",
            "details": {
                "extensions": {"harness_verdict": "APPROVE", "commit_sha": self.sha},
            },
            "attachments": [{"kind": "report", "ref": f"store/reports/{self.sha}.json"}],
        }
        ok, err, meta = run_step_verify(5, "pass", result, config={}, data_dir=self.tmp)
        self.assertTrue(ok, err)
        self.assertEqual(meta.get("harness_verdict"), "APPROVE")


class TestPublishToPlanner(unittest.TestCase):
    def test_warn_report_plans_review_and_acceptance(self):
        out = plan_tier0({
            "mode": "auto",
            "task_type": "code_review",
            "tier": "S",
            "extensions": {
                "harness": {
                    "aggregate_status": "warn",
                    "commit_sha": "d" * 40,
                    "layers": {"static_analysis": {"semgrep": {"findings": 0}}},
                },
            },
        })
        rts = [x["role_type"] for x in out["planned_chain"]]
        self.assertEqual(rts[0], 5)
        self.assertIn(12, rts)


if __name__ == "__main__":
    unittest.main()
