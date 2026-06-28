#!/usr/bin/env python3
"""列出 agent inbox 中 pending/processing 消息摘要。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.utils import json_read, resolve_paths
from lib.models import Inbox


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(MAIL, "store"))
    ap.add_argument("--agent", required=True)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    paths = resolve_paths(args.data_dir)
    data = json_read(f"{paths['inbox']}/{args.agent}/inbox.json", {}, ttl=0)
    inbox = Inbox.from_dict(data) if data else Inbox(agent=args.agent)
    active = ("pending", "pushed", "processing", "resending", "sent")
    n = 0
    for m in inbox.messages:
        st = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if st not in active:
            continue
        mid = inbox.msg_field(m, "id", "")
        mtype = inbox.msg_field(m, "type", "")
        content = (inbox.msg_field(m, "content", "") or "")[:80].replace("\n", " ")
        print(f"  [{st}] {mtype} {mid}: {content}")
        n += 1
        if n >= args.limit:
            break
    print(f"shown {n} active (limit {args.limit})")


if __name__ == "__main__":
    main()
