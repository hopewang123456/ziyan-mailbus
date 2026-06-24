#!/usr/bin/env python3
"""video_publish dry_run → live 发布演练 CLI。"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.drill.video_publish import run_video_publish_drill


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--check-n8n", action="store_true")
    args = ap.parse_args()

    mode = "check-n8n" if args.check_n8n else ("live" if args.live else "dry")
    print("== video_publish tool_live drill ==\n")
    result = run_video_publish_drill(args.data_dir, mode=mode, live=args.live)

    for step in result.get("steps") or []:
        mark = "PASS" if step.get("status") == "pass" else ("WARN" if step.get("status") == "warn" else "FAIL")
        detail = step.get("detail", "")
        if not isinstance(detail, str):
            detail = str(detail)[:120]
        else:
            detail = detail[:120]
        print(f"  {mark}  {step.get('id')}: {detail}")

    for w in result.get("warnings") or []:
        print(f"  WARN  {w}")

    if result.get("error"):
        print(f"\nFAILED: {result.get('error')} — {result.get('message')}", file=sys.stderr)
        return 1

    print("\nAll drill checks passed." if result.get("ok") else "\nDrill failed.")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
