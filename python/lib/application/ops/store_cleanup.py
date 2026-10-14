"""Ops: store housekeeping — inbox archive + queue prune (tools 业务下沉)."""
from __future__ import annotations

from lib.infra.clock import now_dt, now_iso, now_ts, now_utc_dt
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from lib.domain.models import Inbox, MsgStatus
from lib.application.scan import _cleanup_stale_queue_files, get_msg_state
from lib.infra.utils import _now_iso, json_read, json_write, resolve_paths

DEFAULT_ARCHIVE_STATUSES: tuple[str, ...] = (
    "done",
    "archived",
    "failed",
    "cancelled",
    "closed",
    "acknowledged",
    "resending",
    "pushed",
    "processing",
)


def parse_msg_time(raw: str) -> datetime | None:
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


def list_store_agents(data_dir: str, only: list[str] | None = None) -> list[str]:
    if only:
        return list(only)
    paths = resolve_paths(data_dir)
    inbox_root = paths["inbox"]
    if not os.path.isdir(inbox_root):
        return []
    return sorted(
        name
        for name in os.listdir(inbox_root)
        if os.path.isfile(os.path.join(inbox_root, name, "inbox.json"))
    )


def archive_inbox_backlog(
    data_dir: str,
    agent: str,
    *,
    older_than_days: int = 7,
    keep_recent: int = 25,
    dry_run: bool = False,
    statuses: tuple[str, ...] = DEFAULT_ARCHIVE_STATUSES,
) -> dict[str, Any]:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": agent, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    cutoff = now_utc_dt() - timedelta(days=older_than_days)

    to_archive: list = []
    keep: list = []
    for msg in inbox.messages:
        st = (inbox.msg_field(msg, "status", "") or "").lower()
        if st not in statuses and st != MsgStatus.PENDING:
            keep.append(msg)
            continue
        ts = inbox.msg_field(msg, "timestamp", "") or inbox.msg_field(msg, "created_at", "") or ""
        dt = parse_msg_time(ts)
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
    stamp = now_dt().strftime("%Y%m%d-%H%M%S")
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
) -> dict[str, Any]:
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
