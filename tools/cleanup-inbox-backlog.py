#!/usr/bin/env python3
"""批量清理 agent inbox 积压：notice/催办/已关闭消息标记 done。"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, resolve_paths, _now_iso

SKIP_TYPES = {"task"}
AUTO_DONE_PATTERNS = (
    "inbox_overflow",
    "催办提醒",
    "超时提醒",
    "团队规范已更新",
    "team-secrets-policy",
    "execution-order.md",
    "key_missing",
    "API Key 缺失",
)
AUTO_DONE_PREFIX = ("remind-", "tracker-remind", "timeout-")


def should_auto_done(mid: str, mtype: str, content: str, state: str) -> bool:
    if state in (MsgStatus.DONE, "closed"):
        return True
    if mtype == "notice":
        if any(p in content for p in AUTO_DONE_PATTERNS):
            return True
        if mid.startswith(AUTO_DONE_PREFIX):
            return True
    if mtype != "task":
        if mid.startswith(AUTO_DONE_PREFIX):
            return True
    return False


def cleanup_agent(data_dir: str, agent: str, *, dry_run: bool = False) -> int:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    if not data:
        return 0
    inbox = Inbox.from_dict(data)
    closed = 0
    ts = _now_iso()
    for m_raw in inbox.messages:
        mid = inbox.msg_field(m_raw, "id", "")
        mtype = inbox.msg_field(m_raw, "type", "")
        content = inbox.msg_field(m_raw, "content", "")
        state = inbox.msg_field(m_raw, "state", "") or inbox.msg_field(m_raw, "status", "")
        if mtype in SKIP_TYPES and state not in ("closed", MsgStatus.DONE):
            continue
        if not should_auto_done(mid, mtype, content, state):
            continue
        if dry_run:
            closed += 1
            continue
        inbox.set_msg_status(
            mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
            done_at=ts, done_note="auto: backlog cleanup",
        )
        closed += 1
    if closed and not dry_run:
        json_write(inbox_file, inbox.to_dict())
    return closed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="/mailbus/store")
    ap.add_argument("--agents", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from lib.commands import load_config
    cfg = load_config(os.path.join(args.data_dir, "config.json"))
    agents = args.agents or list(cfg.get("agents", {}).keys())
    total = 0
    for name in agents:
        n = cleanup_agent(args.data_dir, name, dry_run=args.dry_run)
        if n:
            print(f"  {name}: {'would close' if args.dry_run else 'closed'} {n}")
        total += n
    print(f"合计 {total} 条")


if __name__ == "__main__":
    main()
