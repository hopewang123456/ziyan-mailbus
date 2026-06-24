#!/usr/bin/env python3
"""清理 inbox 积压：将陈旧 notice / 催办 / 团队规范消息标记 done，并触发归档。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.archiver import archive_all
from lib.models import Inbox, MsgStatus
from lib.commands import load_config
from lib.utils import json_read, json_write, resolve_paths, _now_iso

NOTICE_KEYS = (
    "团队规范已更新", "team-secrets-policy", "execution-order.md",
    "inbox_overflow", "催办提醒", "tracker-remind", "超时提醒",
)
REMIND_PREFIXES = ("remind-", "tracker-remind", "exec-remind-", "reply-patrol-")


def prune_agent(data_dir: str, agent: str, *, dry_run: bool = False) -> int:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return 0
    inbox = Inbox.from_dict(inbox_data)
    changed = 0
    ts = _now_iso()
    for m_raw in inbox.messages:
        state = inbox.msg_field(m_raw, "state", "") or inbox.msg_field(m_raw, "status", "")
        if state in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.ARCHIVED):
            continue
        mtype = inbox.msg_field(m_raw, "type", "")
        mid = inbox.msg_field(m_raw, "id", "")
        content = inbox.msg_field(m_raw, "content", "") or ""
        action = inbox.msg_field(m_raw, "action", {}) or {}
        execute = action.get("execute", mtype == "task") if action else (mtype == "task")
        if mtype == "task" and execute:
            continue
        if mtype != "notice" and not any(k in content for k in NOTICE_KEYS) and not any(
            mid.startswith(p) for p in REMIND_PREFIXES
        ):
            continue
        if dry_run:
            changed += 1
            continue
        if inbox.set_msg_status(
            mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
            done_at=ts, done_note="auto: inbox prune notice",
        ):
            changed += 1
    if changed and not dry_run:
        json_write(inbox_file, inbox.to_dict())
    return changed


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(MAIL, "store"))
    ap.add_argument("--agent", default="", help="指定 agent，默认全员")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--archive", action="store_true", help="清理后执行 archive")
    args = ap.parse_args()

    config = load_config(os.path.join(args.data_dir, "config.json"))
    agents = config.get("agents", {})
    targets = [args.agent] if args.agent else list(agents.keys())
    total = 0
    for name in targets:
        n = prune_agent(args.data_dir, name, dry_run=args.dry_run)
        if n:
            print(f"  {name}: pruned {n} notice(s)")
        total += n
    print(f"total pruned: {total}" + (" (dry-run)" if args.dry_run else ""))

    if args.archive and not args.dry_run:
        archived = archive_all(
            args.data_dir, agents,
            archive_days=config.get("archive_days", 7),
            max_messages=config.get("archive_max_messages", 300),
        )
        if archived:
            for k, v in archived.items():
                print(f"  archived {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
