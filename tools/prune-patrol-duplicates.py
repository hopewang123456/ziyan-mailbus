#!/usr/bin/env python3
"""合并重复巡检 task：lingxun inbox 只保留最新一条 patrol，其余标记 done。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths, _now_iso

PATROL_MARKERS = ("执行定时巡检", "定时巡检", "巡检报告")
REPLY_PATROL_PREFIX = "reply-patrol-"
ACTIVE = frozenset({"pending", "pushed", "processing", "resending", "sent", "received", "acknowledged"})


def _is_patrol_backlog(mid: str, content: str, mtype: str) -> bool:
    if mid.startswith(REPLY_PATROL_PREFIX) or mid.startswith("patrol-"):
        return True
    if mtype == "task" and any(x in content for x in PATROL_MARKERS):
        return True
    if mtype == "reply" and "巡检报告" in content:
        return True
    return False


def dedupe_patrol(data_dir: str, agent: str = "lingxun", *, dry_run: bool = False) -> int:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {}, ttl=0)
    if not data:
        return 0
    inbox = Inbox.from_dict(data)
    patrols = []
    for m in inbox.messages:
        mid = inbox.msg_field(m, "id", "")
        content = inbox.msg_field(m, "content", "") or ""
        mtype = inbox.msg_field(m, "type", "")
        if not _is_patrol_backlog(mid, content, mtype):
            continue
        st = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if st in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.ARCHIVED, "done", "closed"):
            continue
        patrols.append(m)

    if not patrols:
        return 0

    # 保留最新一条 patrol-* notice，其余全部关闭
    def sort_key(m):
        mid = inbox.msg_field(m, "id", "")
        if mid.startswith("patrol-") and not mid.startswith(REPLY_PATROL_PREFIX):
            return ("0", inbox.msg_field(m, "created_at", "") or mid)
        return ("1", inbox.msg_field(m, "created_at", "") or mid)

    patrols.sort(key=sort_key, reverse=True)
    keep = None
    for m in patrols:
        mid = inbox.msg_field(m, "id", "")
        if mid.startswith("patrol-") and not mid.startswith(REPLY_PATROL_PREFIX):
            keep = mid
            break
    closed = 0
    ts = _now_iso()
    for m in patrols:
        mid = inbox.msg_field(m, "id", "")
        if keep and mid == keep:
            continue
        if dry_run:
            closed += 1
            continue
        if inbox.set_msg_status(
            mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
            done_at=ts, done_note="auto: patrol backlog cleanup",
        ):
            closed += 1
    if closed and not dry_run:
        json_write(inbox_file, inbox.to_dict())
    return closed


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(MAIL, "store"))
    ap.add_argument("--agent", default="lingxun")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    n = dedupe_patrol(args.data_dir, args.agent, dry_run=args.dry_run)
    print(f"{'would close' if args.dry_run else 'closed'} {n} duplicate patrol(s) for {args.agent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
