#!/usr/bin/env python3
"""暂停 V3 验收任务，为 FSM 改造让路。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.task_fsm import apply_pause, ensure_fsm, fsm_summary
from lib.utils import json_write

TASK_ID = "game-stellar-v3-20260617"
DATA_DIR = os.path.join(MAIL, "store")

def main():
    from lib.tracker import TaskTracker
    tracker = TaskTracker(DATA_DIR)
    task = tracker.get(TASK_ID)
    if not task:
        print(f"task not found: {TASK_ID}")
        return 1
    outcome = apply_pause(task, reason="FSM 改造期间暂停 V3 验收，改造完成后再恢复")
    json_write(os.path.join(DATA_DIR, "tasks", f"{TASK_ID}.json"), task)
    print("paused:", TASK_ID)
    print(fsm_summary(task))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
