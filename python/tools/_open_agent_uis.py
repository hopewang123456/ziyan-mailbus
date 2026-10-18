#!/usr/bin/env python3
"""Open browsers + try CLI terminals for hermes/openclaw (+ sample others)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from tools.ops.launch_agent import launch_agent  # noqa: E402

DATA = str(ROOT / "shared" / "store")

# Browser: all hermes + openclaw + samples of the rest
BROWSERS = [
    "lingzhao",
    "lingjin",
    "lingtuo",
    "lingxi",
    "lingxun",
    "lingzhang",
    "xiaoqi",
    "yige",
    "lingxiao",
    "lingyun",
]

# Terminal/CLI: one per framework pair (avoid flooding)
CLIS = [
    "lingzhao",
    "lingjin",
    "xiaoqi",
    "yige",
]


def main() -> int:
    print("=== browser ===")
    for aid in BROWSERS:
        rc = launch_agent(aid, "browser", DATA)
        print(f"  browser {aid}: rc={rc}")
        time.sleep(0.4)

    print("\n=== cli / terminal ===")
    for aid in CLIS:
        rc = launch_agent(aid, "cli", DATA)
        print(f"  cli {aid}: rc={rc}")
        time.sleep(0.6)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
