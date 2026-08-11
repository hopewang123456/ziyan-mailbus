#!/usr/bin/env python3
"""从 launch-agent.sh 启动 agent Desktop App。"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.adapters.frameworks.desktop_launch import launch_desktop


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    args = ap.parse_args()
    try:
        result = launch_desktop(args.agent, args.data_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
