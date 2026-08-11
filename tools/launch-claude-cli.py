#!/usr/bin/env python3
"""CLI: 启动 Claude Code 交互终端（Windows PowerShell 弹窗）。"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.adapters.frameworks.claude_launch import launch_claude_cli


def main() -> int:
    p = argparse.ArgumentParser(description="Launch Claude Code interactive CLI")
    p.add_argument("agent")
    p.add_argument("--data-dir", default=os.environ.get("DATA_DIR") or os.path.join(ROOT, "store"))
    args = p.parse_args()
    try:
        info = launch_claude_cli(args.agent, args.data_dir)
        print(json.dumps(info, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
