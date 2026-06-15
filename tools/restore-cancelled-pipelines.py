#!/usr/bin/env python3
"""恢复被 orchestrator 误 cancel 的 pipeline + 主任务 inbox 消息。"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.execution_orchestrator import restore_cancelled_task, _primary_task_id
from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths

DATA = os.environ.get("MAILBUS_DATA", "store")


def main():
    primary = _primary_task_id(DATA)
    restored = 0

    # 恢复主任务关联的 msg-* tracker（如 msg-25601）
    for path in glob.glob(os.path.join(DATA, "tasks", "msg-*.json")):
        t = json.load(open(path, encoding="utf-8"))
        if t.get("status") != "cancelled":
            continue
        tid = t.get("task_id", "")
        reason = t.get("cancel_reason") or ""
        summary = t.get("summary") or ""
        if primary and (primary in summary or "Round1" in summary or "scheduler-validation" in summary):
            if restore_cancelled_task(DATA, tid, "restore primary pipeline msg"):
                print(f"  restored task {tid}")
                restored += 1
            continue
        if "dedupe: primary pipeline" in reason:
            if restore_cancelled_task(DATA, tid, "undo aggressive dedupe"):
                print(f"  restored task {tid}")
                restored += 1

    # 主任务 inbox 消息 reset pending
    if primary:
        paths = resolve_paths(DATA)
        for agent in ("lingzhao",):
            inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
            inbox_data = json_read(inbox_file, {})
            if not inbox_data:
                continue
            inbox = Inbox.from_dict(inbox_data)
            changed = False
            for m in inbox.messages:
                content = inbox.msg_field(m, "content", "")
                if primary not in content:
                    continue
                state = inbox.msg_field(m, "state", "")
                if state in (MsgStatus.DONE, MsgStatus.PENDING):
                    mid = inbox.msg_field(m, "id", "")
                    if inbox.set_msg_status(
                        mid, MsgStatus.PENDING, state=MsgStatus.PENDING,
                        pushed_count=0, done_at=None,
                    ):
                        inbox.has_unread = True
                        changed = True
                        print(f"  reset inbox {agent} {mid} -> pending")
            if changed:
                json_write(inbox_file, inbox.to_dict())

    print(f"=== restored {restored} cancelled task(s), primary={primary} ===")


if __name__ == "__main__":
    main()
