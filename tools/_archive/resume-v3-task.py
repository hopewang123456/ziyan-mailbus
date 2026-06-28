#!/usr/bin/env python3
"""恢复 V3 验收任务（FSM 改造完成后）。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.task_fsm import TaskFsmState, ensure_fsm, fsm_summary
from lib.utils import json_write

TASK_ID = "game-stellar-v3-20260617"
DATA_DIR = os.path.join(MAIL, "store")
DEFAULT_PRIORITY = 10  # 高优先级，便于验收


def main():
    from lib.tracker import TaskTracker

    tracker = TaskTracker(DATA_DIR)
    task = tracker.get(TASK_ID)
    if not task:
        print(f"task not found: {TASK_ID}")
        return 1

    ensure_fsm(task)
    task["fsm"]["state"] = TaskFsmState.EXECUTING.value
    task["fsm"]["priority"] = DEFAULT_PRIORITY
    task["status"] = "running"
    task.pop("pause_reason", None)
    json_write(os.path.join(DATA_DIR, "tasks", f"{TASK_ID}.json"), task)
    print("resumed:", TASK_ID, "priority=", DEFAULT_PRIORITY)
    print(fsm_summary(task))
    print("\n下一步: python3 tools/repush-v3-step5.py  或等待 scan 自动推送 Step5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
