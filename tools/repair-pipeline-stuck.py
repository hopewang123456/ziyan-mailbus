#!/usr/bin/env python3
"""CLI: repair stuck pipeline — delegates to application.ops (Wave5)."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.ops.repair_pipeline import fix_stuck_pipeline, report_stuck_pipeline


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="store")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    info = report_stuck_pipeline(args.data_dir, args.task_id)
    print(json.dumps(info, ensure_ascii=False, indent=2))

    if args.fix:
        result = fix_stuck_pipeline(args.data_dir, args.task_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("  ✓ repair 完成")

    issues = []
    if not info["has_msg_results"]:
        issues.append("无 msg-results")
    if info["duplicate_trackers"]:
        issues.append(f"{len(info['duplicate_trackers'])} 条重复 tracker")
    if info["stale_queues"]:
        issues.append("stale queue")
    if info["phantom_replies"]:
        issues.append("phantom reply（口头完成未落盘）")
    if info["inbox_missing_task"]:
        issues.append("inbox 无 task 消息")

    if issues:
        print(f"  问题: {', '.join(issues)}")
        return 1
    print("  OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
