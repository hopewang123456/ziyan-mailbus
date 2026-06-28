#!/usr/bin/env python3
"""关闭 stale pending inbox：success/cancelled 任务、超时未执行、success pipeline 残留。"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, MsgStatus
from lib.tracker import TaskTracker, _parse_iso_dt
from lib.utils import json_read, json_write, resolve_paths, _now_iso


def _task_terminal_statuses(data_dir: str) -> dict:
    out = {}
    for t in TaskTracker(data_dir).list_all():
        tid = t.get("task_id", "")
        if tid:
            out[tid] = t.get("status", "")
    return out


def close_stale_pending(
    data_dir: str,
    agents: list[str],
    *,
    stale_days: int = 3,
    dry_run: bool = False,
) -> dict:
    paths = resolve_paths(data_dir)
    terminal = _task_terminal_statuses(data_dir)
    terminal_ok = {k for k, v in terminal.items() if v in ("success", "cancelled", "failed", "timeout")}
    now = datetime.now(timezone.utc)
    ts = _now_iso()
    stats = {}

    for agent in agents:
        inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
        data = json_read(inbox_file, {})
        if not data:
            continue
        inbox = Inbox.from_dict(data)

        # 定时巡检：只保留最新 1 条 pending，其余关闭
        patrol_pending = []
        for m_raw in inbox.messages:
            content = inbox.msg_field(m_raw, "content", "")
            state = inbox.msg_field(m_raw, "state", "") or inbox.msg_field(m_raw, "status", "")
            if state == MsgStatus.PENDING and "执行定时巡检" in content:
                patrol_pending.append(m_raw)
        if len(patrol_pending) > 1:
            patrol_pending.sort(
                key=lambda m: inbox.msg_field(m, "created_at", ""), reverse=True,
            )
            for m_raw in patrol_pending[1:]:
                mid = inbox.msg_field(m_raw, "id", "")
                if not dry_run:
                    inbox.set_msg_status(
                        mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                        done_at=ts, done_note="auto: stale patrol dedup",
                    )
                stats[agent] = stats.get(agent, 0) + 1

        closed = 0
        for m_raw in inbox.messages:
            mid = inbox.msg_field(m_raw, "id", "")
            state = inbox.msg_field(m_raw, "state", "") or inbox.msg_field(m_raw, "status", "")
            if state not in (MsgStatus.PENDING, MsgStatus.PROCESSING, "pending", "processing"):
                continue

            content = inbox.msg_field(m_raw, "content", "")
            mtype = inbox.msg_field(m_raw, "type", "")
            created = inbox.msg_field(m_raw, "created_at", "")
            reason = None

            for tid in terminal_ok:
                if tid in content:
                    reason = f"task {terminal[tid]}: {tid}"
                    break

            if not reason and ("key_missing" in content or "API Key 缺失" in content):
                reason = "resolved key_missing notice"

            if not reason and state in (MsgStatus.PROCESSING, "processing"):
                if (mtype or "notice") == "notice":
                    reason = "stale notice processing"

            if not reason and created:
                try:
                    age = (now - _parse_iso_dt(created).astimezone(timezone.utc)).days
                    if age >= stale_days and mtype == "task":
                        has_running = any(
                            terminal.get(tid) == "running" and tid in content
                            for tid in terminal
                        )
                        if not has_running:
                            reason = f"stale pending {age}d"
                except Exception:
                    pass

            if not reason:
                continue

            if dry_run:
                closed += 1
                continue

            inbox.set_msg_status(
                mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                done_at=ts, done_note=f"auto: {reason}",
            )
            closed += 1

        if closed and not dry_run:
            json_write(inbox_file, inbox.to_dict())
        elif stats.get(agent) and not dry_run:
            json_write(inbox_file, inbox.to_dict())
        if closed:
            stats[agent] = stats.get(agent, 0) + closed

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="/mailbus/store")
    ap.add_argument("--agents", nargs="*", default=None)
    ap.add_argument("--stale-days", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from lib.commands import load_config
    cfg = load_config(os.path.join(args.data_dir, "config.json"))
    agents = args.agents or list(cfg.get("agents", {}).keys())

    stats = close_stale_pending(
        args.data_dir, agents, stale_days=args.stale_days, dry_run=args.dry_run,
    )
    total = sum(stats.values())
    for a, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {'would close' if args.dry_run else 'closed'} {a}: {n}")
    print(f"total: {total}")


if __name__ == "__main__":
    main()
