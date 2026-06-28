#!/usr/bin/env python3
"""inbox 积压 triage：统计 notice/催办类消息，可选归档旧 notice。"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths, _now_iso

NOTICE_PREFIXES = (
    "tracker-remind-", "remind-", "rule-change-", "patrol-", "heartbeat-",
    "confirm-", "alert-task-", "max-push-",
)
DONE_STATES = {MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.ARCHIVED, "done", "closed", "archived"}


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def triage_agent(data_dir: str, agent: str, *, days: int, dry_run: bool) -> dict:
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], agent, "inbox.json")
    data = json_read(inbox_file, {})
    if not data:
        return {"agent": agent, "total": 0, "archived": 0}

    inbox = Inbox.from_dict(data)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    archived = 0
    stats = {"pending": 0, "notice": 0, "task": 0, "old_notice": 0}

    for m in inbox.messages:
        mtype = (inbox.msg_field(m, "type", "") or "notice").lower()
        state = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        mid = inbox.msg_field(m, "id", "") or ""

        if state in DONE_STATES:
            continue
        stats["pending"] += 1
        if mtype == "task":
            stats["task"] += 1
            continue
        stats["notice"] += 1

        is_noise = any(mid.startswith(p) for p in NOTICE_PREFIXES) or mtype == "notice"
        created = _parse_ts(inbox.msg_field(m, "created_at", "") or "")
        if is_noise and created and created < cutoff:
            stats["old_notice"] += 1
            if not dry_run:
                inbox.set_msg_status(
                    mid, MsgStatus.ACKNOWLEDGED,
                    state=MsgStatus.DONE,
                    done_at=_now_iso(),
                    done_note=f"triage-inbox-backlog>{days}d",
                )
                archived += 1

    if archived and not dry_run:
        json_write(inbox_file, inbox.to_dict())

    return {"agent": agent, "total": len(inbox.messages), "archived": archived, **stats}


def main() -> int:
    p = argparse.ArgumentParser(description="inbox 积压 triage")
    p.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", "store"))
    p.add_argument("--agent", default="", help="单 agent；默认全员")
    p.add_argument("--days", type=int, default=7, help="归档超过 N 天的 notice/催办")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = [args.agent] if args.agent else list((cfg.get("agents") or {}).keys())

    total_archived = 0
    for name in sorted(agents):
        r = triage_agent(data_dir, name, days=args.days, dry_run=args.dry_run)
        total_archived += r.get("archived", 0)
        print(
            f"{r['agent']}: pending={r.get('pending', 0)} notice={r.get('notice', 0)} "
            f"task={r.get('task', 0)} old_notice={r.get('old_notice', 0)} "
            f"archived={r.get('archived', 0)}"
        )
    mode = "dry-run" if args.dry_run else "applied"
    print(f"done ({mode}): archived={total_archived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
