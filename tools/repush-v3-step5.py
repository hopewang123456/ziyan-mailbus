#!/usr/bin/env python3
"""重推 V3 Step5（灵霄）并触发 scan。"""
import os
import subprocess
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)
os.chdir(MAIL)

from lib.commands import load_config, run_scan_once
from lib.models import Inbox, MsgStatus, Priority
from lib.scanner import recover_inbox_stale_states
from lib.utils import json_read, json_write, resolve_paths

TASK_ID = "game-stellar-v3-20260617"
MSG_ID = "msg-20260617-42291"
AGENT = "lingxiao"

config = load_config(os.path.join(MAIL, "store", "config.json"))
data_dir = config["data_dir"]
agents = config.get("agents", {})
paths = resolve_paths(data_dir)

# 1) bus retry 重置
subprocess.run(
    [sys.executable, "-m", "bus", "retry", "--msg-id", MSG_ID],
    cwd=MAIL,
    check=False,
)

# 2) 提升优先级、清零计数
inbox_file = f"{paths['inbox']}/{AGENT}/inbox.json"
inbox = Inbox.from_dict(json_read(inbox_file, {}))
ok = inbox.set_msg_status(
    MSG_ID,
    MsgStatus.PENDING,
    state=MsgStatus.PENDING,
    priority=Priority.URGENT,
    pushed_count=0,
    reminded_count=0,
    done_at=None,
    done_note=None,
    acknowledged_at=None,
    received_at=None,
    last_pushed_at=None,
)
if ok:
    json_write(inbox_file, inbox.to_dict())
    print(f"✓ {MSG_ID} → pending + urgent")
else:
    print(f"✗ 未找到 {MSG_ID}")

# 3) 回收僵尸 inbox 状态
stats = recover_inbox_stale_states(data_dir, agents)
print(f"recover: {stats}")

# 4) 确认 task Step5 仍在 running
from lib.tracker import TaskTracker

task = TaskTracker(data_dir).get(TASK_ID)
if task:
    chain = task.get("chain") or []
    cur = chain[-1] if chain else {}
    print(f"task status={task.get('status')} step={cur.get('step')} assignee={cur.get('to_person')} step_status={cur.get('status')}")
else:
    print(f"✗ task not found: {TASK_ID}")

# 5) 触发 scan
print("--- scan ---")
run_scan_once(data_dir, config, quiet=False)
