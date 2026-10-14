"""auto-revert.py 单元测试（mock git）。"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
_AUTO_REVERT_PATH = ROOT / "tools" / "harness" / "auto-revert.py"
_spec = importlib.util.spec_from_file_location("auto_revert", _AUTO_REVERT_PATH)
assert _spec and _spec.loader
_ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ar)

should_revert = _ar.should_revert
revert_failed_commit = _ar.revert_failed_commit
revert_marker_path = _ar.revert_marker_path


class TestAutoRevert(unittest.TestCase):
    def test_should_revert_only_fail_and_enable(self) -> None:
        report = {"aggregate_status": "fail"}
        self.assertTrue(should_revert(report, enable=True))
        self.assertFalse(should_revert(report, enable=False))
        self.assertFalse(should_revert({"aggregate_status": "warn"}, enable=True))
        self.assertFalse(should_revert({"aggregate_status": "pass"}, enable=True))

    def test_revert_success_with_stash(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        repo.mkdir()
        report_dir = tmp / "reports"
        sha = "abc123def456"

        calls: list[list[str]] = []

        def run_git(args: list[str], cwd: Path, *, check: bool = False):
            calls.append(args)
            mapping = {
                ("rev-parse", "--verify", sha): MagicMock(returncode=0, stdout=sha, stderr=""),
                ("rev-parse", "HEAD"): MagicMock(returncode=0, stdout=sha, stderr=""),
                ("rev-parse", "--verify", f"{sha}^"): MagicMock(returncode=0, stdout="parent111", stderr=""),
                ("status", "--porcelain"): MagicMock(returncode=0, stdout=" M foo.py\n", stderr=""),
                ("stash", "push", "-m", "harness-auto-revert pre-revert"): MagicMock(returncode=0, stdout="", stderr=""),
                ("reset", "--hard", "HEAD~1"): MagicMock(returncode=0, stdout="", stderr=""),
                ("stash", "pop"): MagicMock(returncode=0, stdout="", stderr=""),
            }
            return mapping[tuple(args)]

        result = revert_failed_commit(repo, sha, report_dir, run_git=run_git)
        self.assertTrue(result["reverted"])
        self.assertEqual(result["parent_sha"], "parent111")
        marker = revert_marker_path(report_dir, sha)
        self.assertTrue(marker.is_file())
        payload = json.loads(marker.read_text(encoding="utf-8"))
        self.assertEqual(payload["commit_sha"], sha)
        self.assertIn(("stash", "push", "-m", "harness-auto-revert pre-revert"), [tuple(c) for c in calls])
        self.assertIn(["reset", "--hard", "HEAD~1"], calls)

    def test_revert_idempotent_marker(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        repo.mkdir()
        report_dir = tmp / "reports"
        sha = "deadbeef"
        marker = revert_marker_path(report_dir, sha)
        report_dir.mkdir(parents=True)
        marker.write_text("{}", encoding="utf-8")

        def run_git(args: list[str], cwd: Path, *, check: bool = False):
            return MagicMock(returncode=0, stdout=sha, stderr="")

        result = revert_failed_commit(repo, sha, report_dir, run_git=run_git)
        self.assertFalse(result["reverted"])
        self.assertEqual(result["reason"], "already_reverted")

    def test_revert_head_mismatch(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        repo.mkdir()
        report_dir = tmp / "reports"
        sha = "aaa111"

        def run_git(args: list[str], cwd: Path, *, check: bool = False):
            if args == ["rev-parse", "--verify", sha]:
                return MagicMock(returncode=0, stdout=sha, stderr="")
            if args == ["rev-parse", "HEAD"]:
                return MagicMock(returncode=0, stdout="bbb222", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        result = revert_failed_commit(repo, sha, report_dir, run_git=run_git)
        self.assertFalse(result["reverted"])
        self.assertEqual(result["reason"], "head_mismatch")

    def test_main_skips_without_enable(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        report_path = Path(tmp) / "r.json"
        report_path.write_text(
            json.dumps(
                {
                    "schema": "code-review-report-v1",
                    "commit_sha": "abc",
                    "aggregate_status": "fail",
                }
            ),
            encoding="utf-8",
        )
        proc = __import__("subprocess").run(
            [sys.executable, str(_AUTO_REVERT_PATH), "--report", str(report_path)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("skip auto-revert", proc.stdout)


if __name__ == "__main__":
    unittest.main()
