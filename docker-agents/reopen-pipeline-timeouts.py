#!/usr/bin/env python3
"""恢复误标 timeout 的 pipeline 任务，并打印状态摘要。"""
import json
import os
import sys

MAIL = os.environ.get("MAIL_DIR", "/mnt/e/ai_tools/mail")
if sys.platform == "win32":
    MAIL = os.environ.get("MAIL_DIR", r"E:\ai_tools\mail")

sys.path.insert(0, MAIL)
os.chdir(MAIL)

from lib.utils import load_config, json_read
from lib.tracker import TaskTracker, TaskStatus

config = load_config(os.path.join(MAIL, "store", "config.json"))
data_dir = config["data_dir"]
agents = config.get("agents", {})
tracker = TaskTracker(data_dir)

reopened = tracker.reopen_stale_timeouts(agents, data_dir)
print(f"reopened: {reopened}")

for tid in (
    "mailbus-hardening-20260616",
    "game-lvup-20260615-171754",
    "game-lvup-20260615-171010",
    "msg-20260615-04794",
    "msg-20260615-66049",
):
    t = tracker.get(tid)
    if t:
        print(f"  {tid}: status={t.get('status')} reminded={t.get('reminded_count')}")

from collections import Counter
c = Counter()
for f in os.listdir(tracker.tasks_dir):
    if f.endswith(".json"):
        t = json_read(os.path.join(tracker.tasks_dir, f), {})
        c[t.get("status", "?")] += 1
print("all statuses:", dict(c))
