#!/usr/bin/env python3
"""Reset stuck pushed/processing inbox for current pipeline assignee."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.models import Inbox, MsgStatus
from lib.task_fsm import get_active_step
from lib.tracker import TaskTracker
from lib.utils import json_read, json_write, resolve_paths, _now_iso

TASK_ID = "game-courier-20260625"


def main() -> int:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
    t = TaskTracker(data_dir).get(TASK_ID) or {}
    step = get_active_step(t) or {}
    agent = step.get("to_agent") or step.get("to_person") or ""
    if not agent:
        print("no assignee")
        return 1
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], agent, "inbox.json")
    inbox = Inbox.from_dict(json_read(inbox_file, {}))
    reset = 0
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "") or ""
        if TASK_ID not in content:
            continue
        mid = inbox.msg_field(m, "id", "")
        state = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if state in (MsgStatus.PUSHED, MsgStatus.PROCESSING, MsgStatus.CLOSED,
                     MsgStatus.DONE, MsgStatus.ACKNOWLEDGED,
                     "pushed", "processing", "closed", "done", "acknowledged"):
            inbox.set_msg_status(
                mid, MsgStatus.PENDING, state=MsgStatus.PENDING,
                pushed_count=0, last_pushed_at=None,
                acknowledged_at=None, received_at=None,
                done_at=None, done_note=None,
                reminded_count=0, exec_reminded_count=0,
                last_reminded_at=None, last_exec_reminded_at=None,
            )
            reset += 1
            print(f"reset {agent} {mid} ({state}) -> pending")
    if reset:
        json_write(inbox_file, inbox.to_dict())
    else:
        print(f"no stuck msgs for {agent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
