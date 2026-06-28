#!/usr/bin/env python3
"""Reset phantom-done inbox msg for game-courier step retry."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.models import Inbox, MsgStatus
from lib.tracker import TaskTracker
from lib.utils import json_read, json_write, resolve_paths, _now_iso

TASK_ID = "game-courier-20260625"
AGENT = "lingzhao"
MSG_ID = "msg-20260625-59463"


def main() -> int:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], AGENT, "inbox.json")
    data = json_read(inbox_file, {})
    inbox = Inbox.from_dict(data)
    reset = 0
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "") or ""
        if TASK_ID not in content:
            continue
        mid = inbox.msg_field(m, "id", "")
        state = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if state in (MsgStatus.DONE, "done", "closed") and not os.path.isfile(
            os.path.join(data_dir, "msg-results", f"{TASK_ID}.json")
        ) and not os.path.isdir(os.path.join(data_dir, "msg-results", TASK_ID)):
            inbox.set_msg_status(
                mid, MsgStatus.PENDING,
                state=MsgStatus.PENDING,
                pushed_count=0,
                done_at="",
                done_note="",
            )
            reset += 1
            print("reset", mid, "-> pending")
        elif mid == MSG_ID:
            inbox.set_msg_field(m, "last_pushed_at", "")
            inbox.set_msg_field(m, "pushed_count", 0)
            print("cleared push cooldown", mid)
    json_write(inbox_file, inbox.to_dict())

    tr = TaskTracker(data_dir)
    t = tr.get(TASK_ID)
    if t:
        if t.get("status") == "pending":
            t["status"] = "running"
        fsm = t.setdefault("fsm", {})
        if fsm.get("state") in ("", "created"):
            fsm["state"] = "executing"
            fsm["substate"] = "executing"
        t["updated_at"] = _now_iso()
        json_write(tr._task_path(TASK_ID), t)
        print("task fsm -> executing")

    msg_tid = os.path.join(data_dir, "tasks", f"{MSG_ID}.json")
    if os.path.isfile(msg_tid):
        mt = json.load(open(msg_tid, encoding="utf-8"))
        if mt.get("status") != "cancelled":
            mt["status"] = "cancelled"
            mt.setdefault("fsm", {})["state"] = "cancelled"
            json.dump(mt, open(msg_tid, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print("cancelled msg tracker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
