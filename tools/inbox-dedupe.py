#!/usr/bin/env python3
"""inbox 按 msg id 去重：保留状态最优的一条。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.models import Inbox
from lib.utils import json_read, json_write, resolve_paths

_STATE_RANK = {
    "": 0, "new": 1, "pending": 1, "sent": 2, "received": 2, "pushed": 3,
    "acknowledged": 4, "processing": 5, "running": 5, "in_progress": 5,
    "resending": 5, "done": 10, "closed": 10, "archived": 10, "failed": 9,
}


def _rank(msg, inbox: Inbox) -> int:
    st = (
        inbox.msg_field(msg, "state", "")
        or inbox.msg_field(msg, "status", "")
        or ""
    ).lower()
    return _STATE_RANK.get(st, 0)


def dedupe_agent(data_dir: str, agent: str, *, dry_run: bool = False) -> int:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {}, ttl=0)
    if not data:
        return 0
    inbox = Inbox.from_dict(data)
    before = len(inbox.messages)
    best = {}
    order = []
    no_id = []
    for m in inbox.messages:
        mid = inbox.msg_field(m, "id", "")
        if not mid:
            no_id.append(m)
            continue
        if mid not in best:
            order.append(mid)
        if mid not in best or _rank(m, inbox) >= _rank(best[mid], inbox):
            best[mid] = m

    inbox.messages = no_id + [best[mid] for mid in order]
    removed = before - len(inbox.messages)
    if removed and not dry_run:
        json_write(inbox_file, inbox.to_dict())
    return removed


def main():
    import argparse
    from lib.commands import load_config

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(MAIL, "store"))
    ap.add_argument("--agent", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config = load_config(os.path.join(args.data_dir, "config.json"))
    agents = config.get("agents", {})
    targets = [args.agent] if args.agent else list(agents.keys())
    total = 0
    for name in targets:
        n = dedupe_agent(args.data_dir, name, dry_run=args.dry_run)
        if n:
            print(f"  {name}: removed {n} duplicate(s)")
        total += n
    print(f"total removed: {total}" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
