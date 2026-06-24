#!/usr/bin/env python3
"""归档 agent inbox 历史积压 — 将旧 pending/done 消息移入 archive。"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths, _now_iso


def archive_inbox_backlog(
    data_dir: str,
    agent: str,
    *,
    older_than_days: int = 7,
    keep_recent: int = 50,
    dry_run: bool = False,
    statuses: tuple[str, ...] = ("done", "archived", "failed", "cancelled"),
) -> dict:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": agent, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    to_archive: list[dict] = []
    keep: list[dict] = []
    for msg in inbox.messages:
        if not isinstance(msg, dict):
            keep.append(msg)
            continue
        st = (msg.get("status") or "").lower()
        if st not in statuses and st != MsgStatus.PENDING:
            keep.append(msg)
            continue
        ts = msg.get("timestamp") or msg.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            keep.append(msg)
            continue
        if dt >= cutoff and len(keep) < keep_recent:
            keep.append(msg)
        else:
            to_archive.append(msg)

    if dry_run:
        return {"agent": agent, "would_archive": len(to_archive), "would_keep": len(keep)}

    if not to_archive:
        return {"agent": agent, "archived": 0, "kept": len(keep)}

    archive_dir = f"{paths['archive']}/{agent}"
    os.makedirs(archive_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_file = f"{archive_dir}/backlog-{stamp}.json"
    json_write(archive_file, {"agent": agent, "archived_at": _now_iso(), "messages": to_archive})

    inbox.messages = keep
    inbox.has_unread = any(
        isinstance(m, dict) and m.get("status") in (MsgStatus.PENDING, MsgStatus.PUSHED, "processing")
        for m in keep
    )
    json_write(inbox_file, inbox.to_dict())
    return {"agent": agent, "archived": len(to_archive), "kept": len(keep), "archive_file": archive_file}


def main():
    p = argparse.ArgumentParser(description="Archive old inbox messages for an agent")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--older-than-days", type=int, default=7)
    p.add_argument("--keep-recent", type=int, default=50)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    out = archive_inbox_backlog(
        args.data_dir,
        args.agent,
        older_than_days=args.older_than_days,
        keep_recent=args.keep_recent,
        dry_run=args.dry_run,
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
