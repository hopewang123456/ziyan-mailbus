#!/usr/bin/env python3
"""CLI: 启动 Claude Code ttyd Web UI 并打开浏览器。"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.adapters.frameworks.claude_browser_launch import ensure_claude_web, launch_claude_browser


def main() -> int:
    p = argparse.ArgumentParser(description="Launch Claude Code browser (ttyd)")
    p.add_argument("agent")
    p.add_argument("--data-dir", default=os.environ.get("DATA_DIR") or os.path.join(ROOT, "store"))
    p.add_argument("--ensure-only", action="store_true", help="Start ttyd without opening browser")
    p.add_argument("--wait", type=int, default=15)
    args = p.parse_args()
    try:
        if args.ensure_only:
            info = ensure_claude_web(args.agent, args.data_dir, wait_seconds=args.wait)
            print(info.get("url") or info)
        else:
            info = launch_claude_browser(args.agent, args.data_dir)
            print(f"Launched {args.agent} claude-ttyd {info.get('url')}")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
