#!/usr/bin/env python3

"""Claude Code push — 兼容入口，委托 tools/ops/agent-push.py。"""

from __future__ import annotations



import runpy

import sys

from pathlib import Path



if __name__ == "__main__":

    target = Path(__file__).resolve().parent / "agent-push.py"

    sys.argv[0] = str(target)

    runpy.run_path(str(target), run_name="__main__")

