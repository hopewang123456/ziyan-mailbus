#!/usr/bin/env python3
"""兼容入口 — 实际逻辑已并入 lib/self_heal.py，由 bus scan 每轮自动执行。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.self_heal import run_self_heal
from lib.utils import json_read

DATA = os.environ.get("MAILBUS_DATA", "store")


def main():
    config = json_read(os.path.join(DATA, "config.json"), {})
    agents = config.get("agents", {})
    print("=== followup-tasks (delegates to self_heal) ===")
    print(run_self_heal(DATA, agents, phase="full"))


if __name__ == "__main__":
    main()
