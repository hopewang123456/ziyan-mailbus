#!/usr/bin/env python3
"""重置灵犀 pipeline 僵尸消息并立即 scan 重推。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths
from lib.commands import load_config
from lib.jobs import run_scan

DATA_DIR = os.environ.get("MAILBUS_DATA_DIR", "/mailbus/store")
CONFIG = os.environ.get("MAILBUS_CONFIG", f"{DATA_DIR}/config.json")
MID = "msg-20260617-32577"

paths = resolve_paths(DATA_DIR)
inbox_file = f"{paths['inbox']}/lingxi/inbox.json"
data = json_read(inbox_file, {})
inbox = Inbox.from_dict(data)
inbox.set_msg_status(
    MID,
    MsgStatus.PENDING,
    state=MsgStatus.PENDING,
    acknowledged_at=None,
    received_at=None,
    pushed_count=0,
    done_at=None,
)
json_write(inbox_file, inbox.to_dict())
print(f"✓ reset {MID} → pending")

cfg = load_config(CONFIG)
rc = run_scan(DATA_DIR, cfg, quiet=False)
print(f"scan rc={rc}")
