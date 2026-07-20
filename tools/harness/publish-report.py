#!/usr/bin/env python3
"""post-commit harness 报告发布到 mailbus（可选创建 code_review task）。

规范：mail/docs/quality-harness-pipeline-spec.md
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_report(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "code-review-report-v1":
        raise ValueError(f"unsupported schema: {data.get('schema')}")
    return data


def _should_create_task(report: dict, statuses: set[str]) -> bool:
    return report.get("aggregate_status") in statuses


def _build_task_body(report: dict, report_path: Path) -> dict:
    sha = report.get("commit_sha", "unknown")
    rel = report_path.as_posix()
    if rel.startswith("/"):
        rel = f"store/reports/{report_path.name}"
    return {
        "task_type": "code_review",
        "tier": "S",
        "mode": "auto",
        "intent": f"审阅 commit {sha[:7]}",
        "initiator": f"agent:{report.get('author_agent', 'unknown')}",
        "artifacts_in": [{"kind": "report", "ref": rel, "label": "post-commit harness 报告"}],
        "extensions": {
            "harness": {
                "commit_sha": sha,
                "trigger": report.get("trigger", "post-commit-harness"),
                "aggregate_status": report.get("aggregate_status"),
                "layers": report.get("layers") or {},
            }
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish code-review report to mailbus")
    ap.add_argument("--report", type=Path, required=True, help="path to code-review-report-v1 JSON")
    ap.add_argument(
        "--create-task-if",
        default="warn,fail",
        help="comma-separated aggregate_status values that trigger POST /api/tasks/create",
    )
    ap.add_argument("--api-base", default="http://127.0.0.1:8787", help="mailbus API base URL")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.report.is_file():
        print(f"ERROR: report not found: {args.report}", file=sys.stderr)
        return 2

    report = _load_report(args.report)
    statuses = {s.strip() for s in args.create_task_if.split(",") if s.strip()}

    print(f"report {args.report.name} aggregate_status={report.get('aggregate_status')}")

    if not _should_create_task(report, statuses):
        print("skip task create (status not in create-task-if)")
        return 0

    body = _build_task_body(report, args.report)
    if args.dry_run:
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return 0

    url = f"{args.api_base.rstrip('/')}/api/tasks/create"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"WARN: mailbus unreachable ({exc}); report remains local only", file=sys.stderr)
        return 0

    print(f"task created: {payload.get('task_id') or payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
