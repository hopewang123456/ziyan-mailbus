#!/usr/bin/env python3
"""inbox 状态统计 + 激进归档（done/closed 超阈值即归档，不等待 3 天）。"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, MsgStatus
from lib.utils import json_read, json_write, jsonl_append, resolve_paths


def count_states(data_dir: str, agents: list[str]) -> None:
    paths = resolve_paths(data_dir)
    for agent in agents:
        d = json_read(f"{paths['inbox']}/{agent}/inbox.json", {})
        if not d:
            print(f"{agent}: empty")
            continue
        inbox = Inbox.from_dict(d)
        c = Counter()
        for m in inbox.messages:
            st = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")
            c[st] += 1
        print(f"{agent}: total={len(inbox.messages)} {dict(c)}")


def aggressive_archive(
    data_dir: str,
    agents: list[str],
    *,
    max_keep: int = 80,
    keep_done: int = 20,
) -> dict:
    """保留 pending/pushed/processing + 最近 keep_done 条 done，其余 done/closed/acknowledged 归档。"""
    paths = resolve_paths(data_dir)
    week = datetime.now().strftime("%Y-W%V")
    results = {}

    for agent in agents:
        inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
        data = json_read(inbox_file, {})
        if not data:
            continue
        inbox = Inbox.from_dict(data)
        active = []
        archivable = []

        for m in inbox.messages:
            st = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")
            if st in (MsgStatus.PENDING, MsgStatus.PUSHED, MsgStatus.PROCESSING, "pending", "pushed", "processing"):
                active.append(m)
            elif st in (MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.ACKNOWLEDGED, "done", "closed", "acknowledged"):
                archivable.append(m)
            else:
                active.append(m)

        # 最近 done 保留（按 done_at / acknowledged_at 降序）
        def sort_key(m):
            return inbox.msg_field(m, "done_at", "") or inbox.msg_field(m, "acknowledged_at", "") or inbox.msg_field(m, "created_at", "")

        archivable.sort(key=sort_key, reverse=True)
        keep_archivable = archivable[:keep_done]
        to_archive = archivable[keep_done:]

        # 若仍超 max_keep，继续裁最旧的 done
        keep = active + keep_archivable
        if len(keep) > max_keep:
            overflow = len(keep) - max_keep
            extra = keep_archivable[-overflow:] if overflow <= len(keep_archivable) else keep_archivable
            to_archive = extra + to_archive
            keep_archivable = keep_archivable[: max(0, len(keep_archivable) - overflow)]
            keep = active + keep_archivable

        if not to_archive:
            continue

        archive_file = f"{paths['archive']}/{agent}/{week}.jsonl"
        os.makedirs(os.path.dirname(archive_file), exist_ok=True)
        for m in to_archive:
            msg_dict = m.to_dict() if hasattr(m, "to_dict") else dict(m)
            msg_dict["state"] = MsgStatus.ARCHIVED
            jsonl_append(archive_file, msg_dict)

        inbox.messages = keep
        if not any(inbox.msg_field(m, "state", "") not in (MsgStatus.DONE, MsgStatus.ARCHIVED, "done") for m in keep):
            inbox.has_unread = False
        json_write(inbox_file, inbox.to_dict())
        results[agent] = len(to_archive)

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="/mailbus/store")
    ap.add_argument("--agents", nargs="*", default=None)
    ap.add_argument("--max-keep", type=int, default=80)
    ap.add_argument("--keep-done", type=int, default=20)
    ap.add_argument("--stats-only", action="store_true")
    args = ap.parse_args()

    from lib.commands import load_config
    cfg = load_config(os.path.join(args.data_dir, "config.json"))
    agents = args.agents or list(cfg.get("agents", {}).keys())

    if args.stats_only:
        count_states(args.data_dir, agents)
        return

    print("=== before ===")
    count_states(args.data_dir, agents)
    results = aggressive_archive(
        args.data_dir, agents, max_keep=args.max_keep, keep_done=args.keep_done,
    )
    print("=== after ===")
    count_states(args.data_dir, agents)
    total = sum(results.values())
    for a, n in sorted(results.items(), key=lambda x: -x[1]):
        print(f"  archived {a}: {n}")
    print(f"total archived: {total}")


if __name__ == "__main__":
    main()
