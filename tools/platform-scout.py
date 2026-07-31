#!/usr/bin/env python3
"""CLI: platform-scout — delegates to application.ops.platform_scout."""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.application.ops.platform_scout import run_scout  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="platform-scout 线索抓取")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--platform", help="仅跑指定 platform id（v2ex / github_issues）")
    ap.add_argument("--dry-run", action="store_true", help="只抓取统计，不写盘")
    args = ap.parse_args()

    try:
        stats = run_scout(args.data_dir, platform_id=args.platform, dry_run=args.dry_run)
    except Exception as exc:
        print(f"[platform-scout] error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
