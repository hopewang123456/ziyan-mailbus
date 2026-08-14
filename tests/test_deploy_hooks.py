"""deploy-hooks 批量安装 post-commit hook 测试。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "tools" / "harness" / "deploy-hooks.py"
INSTALL = ROOT / "tools" / "harness" / "install-hook.py"
TEMPLATE = ROOT / "tools" / "harness" / "post-commit.hook.template"


def _run_script(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd or ROOT,
    )


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True, capture_output=True)


class TestDeployHooks(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_dry_run_lists_targets(self) -> None:
        repo = self.tmp / "proj-a"
        repo.mkdir()
        _init_git_repo(repo)

        proc = _run_script(DEPLOY, "--projects", str(repo), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("dry-run", proc.stdout)
        self.assertIn("proj-a", proc.stdout)
        self.assertNotIn("installed", proc.stdout)
        self.assertFalse((repo / ".git" / "hooks" / "post-commit").exists())

    def test_install_via_projects(self) -> None:
        repo = self.tmp / "proj-b"
        repo.mkdir()
        _init_git_repo(repo)

        proc = _run_script(
            DEPLOY,
            "--projects",
            str(repo),
            "--mailbus-root",
            str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        hook = repo / ".git" / "hooks" / "post-commit"
        self.assertTrue(hook.is_file())
        text = hook.read_text(encoding="utf-8")
        mail_root_posix = str(ROOT.resolve()).replace("\\", "/")
        self.assertIn(mail_root_posix, text)
        self.assertIn('PUBLISH_FLAG="--dry-run"', text)
        self.assertIn("${MAILBUS_PUBLISH:-0}", text)

    def test_install_publish_flag(self) -> None:
        repo = self.tmp / "proj-c"
        repo.mkdir()
        _init_git_repo(repo)

        proc = _run_script(
            DEPLOY,
            "--projects",
            str(repo),
            "--mailbus-root",
            str(ROOT),
            "--publish",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        text = (repo / ".git" / "hooks" / "post-commit").read_text(encoding="utf-8")
        self.assertIn('PUBLISH_FLAG=""', text)
        self.assertNotIn('PUBLISH_FLAG="--dry-run"', text)

    def test_manifest_relative_paths(self) -> None:
        repo = self.tmp / "nested" / "proj-d"
        repo.mkdir(parents=True)
        _init_git_repo(repo)

        manifest = self.tmp / "projects.json"
        manifest.write_text(
            json.dumps(
                {
                    "mailbus_root": str(ROOT),
                    "publish": False,
                    "projects": [{"name": "nested-proj", "repo": "nested/proj-d"}],
                }
            ),
            encoding="utf-8",
        )

        proc = _run_script(DEPLOY, "--manifest", str(manifest), cwd=self.tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("nested-proj", proc.stdout)

        hook = repo / ".git" / "hooks" / "post-commit"
        self.assertTrue(hook.is_file())

    def test_manifest_publish_override(self) -> None:
        repo = self.tmp / "proj-e"
        repo.mkdir()
        _init_git_repo(repo)

        manifest = self.tmp / "pub.json"
        manifest.write_text(
            json.dumps(
                {
                    "mailbus_root": str(ROOT),
                    "publish": False,
                    "projects": [{"repo": str(repo), "publish": True}],
                }
            ),
            encoding="utf-8",
        )

        proc = _run_script(DEPLOY, "--manifest", str(manifest))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (repo / ".git" / "hooks" / "post-commit").read_text(encoding="utf-8")
        self.assertIn('PUBLISH_FLAG=""', text)

    def test_non_git_repo_fails(self) -> None:
        bad = self.tmp / "not-git"
        bad.mkdir()
        proc = _run_script(DEPLOY, "--projects", str(bad), "--dry-run")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("not a git repo", proc.stderr)

    def test_install_hook_template_render(self) -> None:
        """install-hook 单独安装时模板路径替换正确。"""
        repo = self.tmp / "proj-f"
        repo.mkdir()
        _init_git_repo(repo)

        proc = _run_script(
            INSTALL,
            "--repo",
            str(repo),
            "--mailbus-root",
            str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        hook_text = (repo / ".git" / "hooks" / "post-commit").read_text(encoding="utf-8")
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("generate-report.py", hook_text)
        self.assertIn("publish-report.py", hook_text)
        self.assertNotIn("<MAILBUS_WSL_ROOT>", hook_text)
        self.assertIn(str(ROOT.resolve()).replace("\\", "/"), hook_text)
        self.assertIn("Quality Harness", template)
        self.assertIn("generate-report.py", template)


if __name__ == "__main__":
    unittest.main()
