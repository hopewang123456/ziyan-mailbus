#!/usr/bin/env python3
"""兼容入口 — 请优先使用 tools/mailbus.py recover。"""
from __future__ import annotations

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.mailbus import main  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = ["health"]
    raise SystemExit(main(["recover", *args]))
