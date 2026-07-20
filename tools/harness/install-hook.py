#!/usr/bin/env python3
"""安装 Quality Harness post-commit hook 到目标 git 仓库。"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

MAIL_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = MAIL_ROOT / "tools" / "harness" / "post-commit.hook.template"


def main() -> int:
    ap = argparse.ArgumentParser(description="Install mailbus post-commit harness hook")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="target git repository")
    ap.add_argument(
        "--mailbus-root",
        type=Path,
        default=MAIL_ROOT,
        help="mailbus checkout (for publish-report.py path)",
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help="enable real POST (MAILBUS_PUBLISH=1 in hook)",
    )
    args = ap.parse_args()

    repo = args.repo.resolve()
    git_dir = repo / ".git"
    if not git_dir.is_dir():
        print(f"ERROR: not a git repo: {repo}", file=sys.stderr)
        return 2

    hook_path = git_dir / "hooks" / "post-commit"
    if not TEMPLATE.is_file():
        print(f"ERROR: template missing: {TEMPLATE}", file=sys.stderr)
        return 2

    text = TEMPLATE.read_text(encoding="utf-8")
    mailbus = str(args.mailbus_root.resolve()).replace("\\", "/")
    text = text.replace("/mnt/e/ai_tools/mail", mailbus)
    if args.publish:
        text = text.replace('PUBLISH_FLAG="--dry-run"', 'PUBLISH_FLAG=""')
        text = text.replace("${MAILBUS_PUBLISH:-0}", "1")
    hook_path.write_text(text, encoding="utf-8")

    try:
        hook_path.chmod(hook_path.stat().st_mode | 0o111)
    except OSError:
        pass

    print(f"installed {hook_path}")
    print(f"  mailbus_root={mailbus}")
    print(f"  publish={'on' if args.publish else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
