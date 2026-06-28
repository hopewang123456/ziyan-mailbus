#!/usr/bin/env python3
"""关闭已过期的 Round2 验收重复 task（保留最新 pipeline 工单）。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths, _now_iso

STALE_MARKERS = ("【Round2 R2-004】", "Round2 R2-004")


def close_stale(data_dir: str, agent: str = "lingxiao", *, dry_run: bool = False) -> int:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {}, ttl=0)
    if not data:
        return 0
    inbox = Inbox.from_dict(data)
    closed = 0
    ts = _now_iso()
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "") or ""
        if not any(x in content for x in STALE_MARKERS):
            continue
        st = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if st in (MsgStatus.DONE, MsgStatus.CLOSED, "done", "closed"):
            continue
        mid = inbox.msg_field(m, "id", "")
        if dry_run:
            closed += 1
            continue
        if inbox.set_msg_status(
            mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
            done_at=ts, done_note="auto: stale R2-004 closed",
        ):
            closed += 1
    if closed and not dry_run:
        json_write(inbox_file, inbox.to_dict())
    return closed


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(MAIL, "store"))
    ap.add_argument("--agent", default="lingxiao")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    n = close_stale(args.data_dir, args.agent, dry_run=args.dry_run)
    print(f"closed {n} stale R2-004 task(s) for {args.agent}")
