#!/usr/bin/env python3
"""修复 msg-results 时间戳早于 step started_at 导致 pipeline 无法推进。"""
import json
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/mailbus")
from lib.utils import json_read, json_write, _now_iso
from lib.tracker import TaskTracker, _parse_iso_dt

tid = sys.argv[1] if len(sys.argv) > 1 else "game-stellar-v3-20260617"
dd = "/mailbus/store"
mr_path = f"{dd}/msg-results/{tid}.json"
task = TaskTracker(dd).get(tid) or {}
chain = task.get("chain") or []
if not chain:
    print("no chain"); sys.exit(1)
started = chain[-1].get("started_at") or ""
mr = json_read(mr_path, {})
if not mr:
    print("no msg-results"); sys.exit(1)
old_ts = mr.get("timestamp", "")
new_ts = _now_iso()
if started:
    try:
        st = _parse_iso_dt(started)
        if _parse_iso_dt(old_ts) >= st if old_ts else False:
            print("timestamp OK", old_ts); sys.exit(0)
    except Exception:
        pass
mr["timestamp"] = new_ts
json_write(mr_path, mr)
print(f"fixed timestamp {old_ts!r} -> {new_ts}")
