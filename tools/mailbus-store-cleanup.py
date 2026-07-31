#!/usr/bin/env python3
"""CLI: store cleanup — delegates to application.ops.store_cleanup."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.application.ops.store_cleanup import (  # noqa: E402
    archive_inbox_backlog,
    list_store_agents,
    prune_agent_queues,
)
from lib.utils import json_read, resolve_paths  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="mailbus store cleanup (inbox archive + queue prune)")
    p.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", "store"))
    p.add_argument("--older-than-days", type=int, default=7)
    p.add_argument("--keep-recent", type=int, default=25)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--agent", action="append", default=[])
    p.add_argument("--inbox-only", action="store_true")
    p.add_argument("--queues-only", action="store_true")
    args = p.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    agents = list_store_agents(data_dir, args.agent)
    if not agents:
        print("[cleanup] no agents found")
        return 1

    do_inbox = not args.queues_only
    do_queues = not args.inbox_only
    total_archived = 0
    total_pruned = 0
    total_qfiles = 0

    print(f"[cleanup] agents={len(agents)} dry_run={args.dry_run}")
    for agent in agents:
        inbox_path = f"{resolve_paths(data_dir)['inbox']}/{agent}/inbox.json"
        try:
            if not os.path.isfile(inbox_path):
                continue
            if do_inbox:
                before = len(json_read(inbox_path, {}).get("messages", []))
                try:
                    out = archive_inbox_backlog(
                        data_dir,
                        agent,
                        older_than_days=args.older_than_days,
                        keep_recent=args.keep_recent,
                        dry_run=args.dry_run,
                    )
                except OSError as exc:
                    print(f"  {agent} inbox: skip ({exc})")
                    out = {}
                else:
                    key = "would_archive" if args.dry_run else "archived"
                    n = int(out.get(key, 0))
                    total_archived += n
                    after = before - n if not args.dry_run else before
                    if n or before > args.keep_recent:
                        print(f"  {agent} inbox: before={before} {key}={n} after~={after}")

            if do_queues:
                qout = prune_agent_queues(data_dir, agent, dry_run=args.dry_run)
                total_pruned += int(qout.get("pruned", 0))
                total_qfiles += int(qout.get("removed_files", 0))
                if qout.get("pruned") or qout.get("removed_files"):
                    print(
                        f"  {agent} queue: pruned={qout.get('pruned')} "
                        f"removed_files={qout.get('removed_files')} pending={qout.get('pending')}"
                    )
        except OSError as exc:
            print(f"  {agent}: skip ({exc})")

    if do_inbox:
        label = "would_archive" if args.dry_run else "archived"
        print(f"[cleanup] inbox {label}={total_archived}")
    if do_queues:
        print(f"[cleanup] queue pruned={total_pruned} removed_files={total_qfiles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
