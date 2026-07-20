#!/usr/bin/env python3
"""mailbus store  housekeeping — inbox 归档 + queue/urgent 清理。

用法:
  python tools/mailbus-store-cleanup.py --data-dir store
  python tools/mailbus-store-cleanup.py --data-dir store --dry-run
  python tools/mailbus-store-cleanup.py --data-dir store --inbox-only
  python tools/mailbus-store-cleanup.py --data-dir store --queues-only --agent lingzhao
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.models import Inbox, MsgStatus
from lib.scanner import _cleanup_stale_queue_files, get_msg_state
from lib.utils import json_read, json_write, resolve_paths, _now_iso


def _parse_msg_time(raw: str) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def archive_inbox_backlog(
    data_dir: str,
    agent: str,
    *,
    older_than_days: int = 7,
    keep_recent: int = 25,
    dry_run: bool = False,
    statuses: tuple[str, ...] = (
        "done",
        "archived",
        "failed",
        "cancelled",
        "closed",
        "acknowledged",
        "resending",
        "pushed",
        "processing",
    ),
) -> dict:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": agent, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    to_archive: list = []
    keep: list = []
    for msg in inbox.messages:
        st = (inbox.msg_field(msg, "status", "") or "").lower()
        if st not in statuses and st != MsgStatus.PENDING:
            keep.append(msg)
            continue
        ts = inbox.msg_field(msg, "timestamp", "") or inbox.msg_field(msg, "created_at", "") or ""
        dt = _parse_msg_time(ts)
        if dt is None:
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
    archived_payload = [m.to_dict() if hasattr(m, "to_dict") else m for m in to_archive]
    json_write(archive_file, {"agent": agent, "archived_at": _now_iso(), "messages": archived_payload})

    inbox.messages = keep
    inbox.has_unread = any(
        (inbox.msg_field(m, "status", "") or "") in (MsgStatus.PENDING, MsgStatus.PUSHED, "processing")
        for m in keep
    )
    json_write(inbox_file, inbox.to_dict())
    return {"agent": agent, "archived": len(to_archive), "kept": len(keep), "archive_file": archive_file}


def prune_agent_queues(
    data_dir: str,
    agent: str,
    *,
    dry_run: bool = False,
) -> dict:
    """只保留与 inbox pending 对齐的 queue 条目；空文件删除。"""
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    if not os.path.isfile(inbox_file):
        return {"agent": agent, "pruned": 0, "removed_files": 0}

    inbox = Inbox.from_dict(json_read(inbox_file, {}))
    pending_ids = {
        inbox.msg_field(m, "id", "")
        for m in inbox.messages
        if get_msg_state(m) == MsgStatus.PENDING and inbox.msg_field(m, "id", "")
    }

    pruned = 0
    removed_files = 0
    for qkey in ("queue_urgent", "queue_normal"):
        qf = os.path.join(paths[qkey], f"{agent}.json")
        if not os.path.isfile(qf):
            continue
        qmsgs = json_read(qf, [])
        if not isinstance(qmsgs, list):
            qmsgs = []
        kept = [m for m in qmsgs if isinstance(m, dict) and m.get("id") in pending_ids]
        dropped = len(qmsgs) - len(kept)
        pruned += dropped
        if dry_run:
            if not kept and qmsgs:
                removed_files += 1
            continue
        if not kept:
            os.remove(qf)
            removed_files += 1
        elif dropped:
            json_write(qf, kept)

    if not dry_run:
        removed_files += _cleanup_stale_queue_files(data_dir, {agent: {}})
    elif not pending_ids:
        for qkey in ("queue_urgent", "queue_normal"):
            qf = os.path.join(paths[qkey], f"{agent}.json")
            if os.path.isfile(qf):
                removed_files += 1

    return {"agent": agent, "pruned": pruned, "removed_files": removed_files, "pending": len(pending_ids)}


def _list_agents(data_dir: str, only: list[str]) -> list[str]:
    if only:
        return only
    paths = resolve_paths(data_dir)
    inbox_root = paths["inbox"]
    if not os.path.isdir(inbox_root):
        return []
    return sorted(
        name
        for name in os.listdir(inbox_root)
        if os.path.isfile(os.path.join(inbox_root, name, "inbox.json"))
    )


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
    agents = _list_agents(data_dir, args.agent)
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
