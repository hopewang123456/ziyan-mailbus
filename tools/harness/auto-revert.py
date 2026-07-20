#!/usr/bin/env python3
"""post-commit harness 失败时可选回退 commit（stash + reset，幂等）。

仅当 report aggregate_status=fail 且 --enable 时执行；失败不阻塞 commit（exit 0）。
规范：mail/docs/harness-final-plan.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_report(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "code-review-report-v1":
        raise ValueError(f"unsupported schema: {data.get('schema')}")
    return data


def revert_marker_path(report_dir: Path, sha: str) -> Path:
    return report_dir / f".revert-{sha}"


def should_revert(report: dict, *, enable: bool) -> bool:
    return bool(enable and report.get("aggregate_status") == "fail")


def _git(args: list[str], repo: Path, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=check,
    )


def _resolve_sha(repo: Path, sha: str, run_git=_git) -> str:
    if not sha:
        return ""
    proc = run_git(["rev-parse", "--verify", sha], repo)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _working_tree_dirty(repo: Path, run_git=_git) -> bool:
    proc = run_git(["status", "--porcelain"], repo)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def revert_failed_commit(
    repo: Path,
    sha: str,
    report_dir: Path,
    *,
    run_git=_git,
) -> dict:
    """Stash dirty tree, reset HEAD~1 when HEAD matches sha; write idempotency marker."""
    full_sha = _resolve_sha(repo, sha, run_git)
    if not full_sha:
        return {"reverted": False, "reason": "invalid_sha"}

    marker = revert_marker_path(report_dir, full_sha)
    if marker.is_file():
        return {"reverted": False, "reason": "already_reverted"}

    head = run_git(["rev-parse", "HEAD"], repo)
    if head.returncode != 0:
        return {"reverted": False, "reason": "git_head_unavailable", "error": head.stderr.strip()}
    if head.stdout.strip() != full_sha:
        return {"reverted": False, "reason": "head_mismatch", "head": head.stdout.strip()}

    parent = run_git(["rev-parse", "--verify", f"{full_sha}^"], repo)
    if parent.returncode != 0:
        return {"reverted": False, "reason": "no_parent", "error": parent.stderr.strip()}

    stashed = False
    if _working_tree_dirty(repo, run_git):
        stash = run_git(["stash", "push", "-m", "harness-auto-revert pre-revert"], repo)
        if stash.returncode != 0:
            return {"reverted": False, "reason": "stash_failed", "error": stash.stderr.strip()}
        stashed = True

    reset = run_git(["reset", "--hard", "HEAD~1"], repo)
    if reset.returncode != 0:
        if stashed:
            run_git(["stash", "pop"], repo)
        return {"reverted": False, "reason": "reset_failed", "error": reset.stderr.strip()}

    report_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "commit_sha": full_sha,
                "reverted_at": datetime.now(timezone.utc).isoformat(),
                "parent_sha": parent.stdout.strip(),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if stashed:
        pop = run_git(["stash", "pop"], repo)
        if pop.returncode != 0:
            return {
                "reverted": True,
                "reason": "stash_pop_failed",
                "warning": pop.stderr.strip(),
                "parent_sha": parent.stdout.strip(),
            }

    return {"reverted": True, "parent_sha": parent.stdout.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Revert last commit when harness report failed")
    ap.add_argument("--report", type=Path, required=True, help="code-review-report-v1 JSON")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="git repository")
    ap.add_argument("--enable", action="store_true", help="perform revert (default: dry-run skip)")
    args = ap.parse_args()

    if not args.report.is_file():
        print(f"WARN: report not found: {args.report}", file=sys.stderr)
        return 0

    try:
        report = _load_report(args.report)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"WARN: invalid report: {exc}", file=sys.stderr)
        return 0

    if not should_revert(report, enable=args.enable):
        print("skip auto-revert (disabled or aggregate_status != fail)")
        return 0

    sha = report.get("commit_sha") or ""
    repo = args.repo.resolve()
    report_dir = args.report.parent

    try:
        result = revert_failed_commit(repo, sha, report_dir)
    except OSError as exc:
        print(f"WARN: auto-revert failed: {exc}", file=sys.stderr)
        return 0

    if result.get("reverted"):
        print(f"reverted commit {sha[:7]} -> {result.get('parent_sha', '')[:7]}")
        if result.get("warning"):
            print(f"WARN: {result['warning']}", file=sys.stderr)
        return 0

    reason = result.get("reason", "unknown")
    print(f"skip auto-revert ({reason})", file=sys.stderr)
    if result.get("error"):
        print(f"WARN: {result['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
