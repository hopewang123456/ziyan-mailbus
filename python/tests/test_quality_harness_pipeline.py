"""Quality Harness publish-report 与报告 schema 测试。"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_GENERATE_REPORT_PATH = os.path.join(ROOT, "tools", "harness", "generate-report.py")
_spec = importlib.util.spec_from_file_location("generate_report", _GENERATE_REPORT_PATH)
assert _spec and _spec.loader
_gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gr)
build_report = _gr.build_report
run_static_analysis = _gr.run_static_analysis
_merge_status = _gr._merge_status
_apply_baseline_comparison = _gr._apply_baseline_comparison
_load_baseline = _gr._load_baseline
_write_baseline = _gr._write_baseline


class TestQualityHarnessPipeline(unittest.TestCase):
    def test_code_review_report_example_schema(self):
        path = os.path.join(ROOT, "store", "examples", "code-review-report.example.json")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc.get("schema"), "code-review-report-v1")
        self.assertIn("layers", doc)
        self.assertIn(doc.get("aggregate_status"), ("pass", "warn", "fail", "error"))

    def test_publish_report_dry_run(self):
        report = os.path.join(ROOT, "store", "examples", "code-review-report.example.json")
        script = os.path.join(ROOT, "tools", "harness", "publish-report.py")
        proc = subprocess.run(
            [sys.executable, script, "--report", report, "--dry-run"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("code_review", proc.stdout)
        self.assertIn('"mode": "auto"', proc.stdout)

    def test_publish_report_http_ok_creates_task(self):
        import tempfile

        script = os.path.join(ROOT, "tools", "harness", "publish-report.py")
        _pub_spec = importlib.util.spec_from_file_location("publish_report", script)
        assert _pub_spec and _pub_spec.loader
        pub = importlib.util.module_from_spec(_pub_spec)
        _pub_spec.loader.exec_module(pub)

        tmp = tempfile.mkdtemp()
        report_path = os.path.join(tmp, "warn-report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "schema": "code-review-report-v1",
                "commit_sha": "c" * 40,
                "aggregate_status": "warn",
                "author_agent": "agent-g",
                "trigger": "post-commit-harness",
                "timestamp": "2026-06-30T12:00:00Z",
                "layers": {"regression": {"status": "pass"}, "static_analysis": {"status": "warn"}},
            }, f)

        captured: dict = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            resp = MagicMock()
            resp.read.return_value = json.dumps({
                "status": "ok",
                "task_id": "review-ccccc-001",
            }).encode("utf-8")
            resp.__enter__ = lambda s: resp
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        argv = [
            "publish-report.py",
            "--report", report_path,
            "--api-base", "http://127.0.0.1:8787",
        ]
        with patch.object(pub.urllib.request, "urlopen", fake_urlopen):
            with patch.object(sys, "argv", argv):
                rc = pub.main()
        self.assertEqual(rc, 0)
        self.assertIn("/api/tasks/create", captured.get("url", ""))

    def test_generate_report_writes_schema(self):
        script = os.path.join(ROOT, "tools", "harness", "generate-report.py")
        import tempfile
        tmp = tempfile.mkdtemp()
        proc = subprocess.run(
            [sys.executable, script, "--repo", ROOT, "--out", os.path.join(tmp, "r.json"), "--skip-pytest"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(tmp, "r.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc.get("schema"), "code-review-report-v1")
        self.assertIn(doc.get("aggregate_status"), ("pass", "warn", "fail", "skip"))
        self.assertEqual(doc["layers"]["static_analysis"]["status"], "skip")
        self.assertEqual(doc["layers"]["ai_review"]["status"], "skip")

    def test_static_analysis_default_skip(self):
        layer = run_static_analysis(Path(ROOT), pylint=False, mypy=False, semgrep=False)
        self.assertEqual(layer["status"], "skip")

    def test_static_analysis_tools_missing_all_skip(self):
        layer = run_static_analysis(Path(ROOT), pylint=True, mypy=True, semgrep=True)
        self.assertIn("tools", layer)
        for tool in ("pylint", "mypy", "semgrep"):
            self.assertEqual(layer["tools"][tool]["status"], "skip", tool)

    def test_merge_status_priority(self):
        self.assertEqual(_merge_status("pass", "warn", "skip"), "warn")
        self.assertEqual(_merge_status("skip", "fail"), "fail")

    def test_build_report_aggregate_from_layers(self):
        report = build_report(
            Path(ROOT),
            pytest_layer={"status": "pass", "pytest": {}},
            static_layer={"status": "warn", "mypy_errors": 1},
            ai_layer={"status": "skip"},
        )
        self.assertEqual(report["aggregate_status"], "warn")
        self.assertFalse(report["blocking"])

    @patch.object(_gr, "shutil")
    def test_static_analysis_pylint_pass(self, mock_shutil):
        mock_shutil.which.return_value = "/usr/bin/pylint"
        with patch.object(_gr.subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Your code has been rated at 9.50/10\n"
            with patch.object(_gr, "_changed_py_files", return_value=["lib/foo.py"]):
                layer = run_static_analysis(Path(ROOT), pylint=True, mypy=False, semgrep=False)
        self.assertEqual(layer["status"], "pass")
        self.assertEqual(layer["pylint_score"], 9.5)

    def test_generate_report_static_analysis_flag(self):
        script = _GENERATE_REPORT_PATH
        import tempfile
        tmp = tempfile.mkdtemp()
        proc = subprocess.run(
            [sys.executable, script, "--repo", ROOT, "--out", os.path.join(tmp, "r2.json"),
             "--skip-pytest", "--static-analysis"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(tmp, "r2.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertIn("tools", doc["layers"]["static_analysis"])

    def test_baseline_comparison_new_failures(self):
        import tempfile

        tmp = tempfile.mkdtemp()
        repo = Path(tmp)
        (repo / "store" / "reports").mkdir(parents=True)
        _write_baseline(repo, ["tests/test_old.py::test_known_fail"])
        layer = {
            "status": "fail",
            "pytest": {
                "failed_nodeids": [
                    "tests/test_old.py::test_known_fail",
                    "tests/test_new.py::test_regression",
                ],
            },
        }
        out = _apply_baseline_comparison(layer, repo)
        new_failures = out["pytest"]["new_failures_vs_baseline"]
        self.assertEqual(new_failures, ["tests/test_new.py::test_regression"])

    def test_build_report_includes_new_failures_field(self):
        report = build_report(
            Path(ROOT),
            pytest_layer={
                "status": "pass",
                "pytest": {"failed_nodeids": [], "new_failures_vs_baseline": []},
            },
            apply_baseline=False,
        )
        self.assertIn("new_failures_vs_baseline", report["layers"]["regression"]["pytest"])


if __name__ == "__main__":
    unittest.main()
