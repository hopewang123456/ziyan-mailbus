#!/usr/bin/env python3
"""Quick status for game-courier pipeline."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tracker import TaskTracker
from lib.utils import json_read, resolve_paths

tid = sys.argv[1] if len(sys.argv) > 1 else "game-courier-20260625"
t = TaskTracker("store").get(tid) or {}
print("task_status", t.get("status"))
chain = t.get("chain") or []
if chain:
    s = chain[-1]
    print("step", s.get("step"), s.get("to_agent") or s.get("to_person"), s.get("status"), s.get("fsm_state"))
paths = resolve_paths("store")
for agent in ("lingzhao", "lingxi", "xiaoqi", "lingxiao", "dali"):
    inbox = json_read(f"{paths['inbox']}/{agent}/inbox.json", {})
    for m in inbox.get("messages") or []:
        if tid in (m.get("content") or ""):
            st = m.get("state") or m.get("status")
            if st not in ("done", "closed", "archived"):
                print(f"inbox_{agent}", m.get("id"), st)
mr = os.path.join("store", "msg-results", f"{tid}.json")
print("msg-results legacy", os.path.isfile(mr))
step_dir = os.path.join("store", "msg-results", tid)
print("step results", os.listdir(step_dir) if os.path.isdir(step_dir) else [])
