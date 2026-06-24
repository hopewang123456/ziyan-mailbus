#!/usr/bin/env python3
"""Round2 / 审计 / 僵尸 chain 一次性清理。"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.audit_dispatch import reconcile_pending_audits
from lib.models import Inbox, MsgStatus
from lib.tracker import TaskTracker
from lib.utils import json_read, json_write, resolve_paths, _now_iso

ROUND2_TAGS = ("R2-004", "R2-007", "R2-008", "Round2")
SUPERSEDED = "game-stellar-20260616"


def fix_stale_chains(data_dir: str) -> int:
    n = 0
    tra = TaskTracker(data_dir)
    for t in tra.list_all():
        tid = t.get("task_id", "")
        if t.get("status") not in ("success", "cancelled", "failed", "timeout"):
            continue
        chain = t.get("chain") or []
        if not chain:
            continue
        changed = False
        for step in chain:
            if step.get("status") == "running":
                step["status"] = "completed"
                step["completed_at"] = step.get("completed_at") or _now_iso()
                changed = True
        if changed:
            json_write(tra._task_path(tid), t)
            n += 1
            print(f"  chain sync: {tid}")
    return n


def fix_superseded_task(data_dir: str) -> bool:
    tra = TaskTracker(data_dir)
    t = tra.get(SUPERSEDED)
    if not t:
        return False
    t["status"] = "cancelled"
    t["requires_audit"] = False
    if not t.get("audit_log"):
        t["audit_log"] = [{
            "reviewer": "mailbus",
            "result": "waived",
            "summary": "假 success(2/12)，已由 game-stellar-20260617 替代，审计豁免",
            "timestamp": _now_iso(),
        }]
    json_write(tra._task_path(SUPERSEDED), t)
    print(f"  cancelled + audit waived: {SUPERSEDED}")
    return True


def close_round2_inbox(data_dir: str, agents: list[str]) -> int:
    paths = resolve_paths(data_dir)
    ts = _now_iso()
    closed = 0
    r2_results = set()
    mr = os.path.join(data_dir, "msg-results")
    if os.path.isdir(mr):
        for fn in os.listdir(mr):
            if fn.startswith("iteration-r2-") or "R2-008" in fn:
                r2_results.add(fn)

    for agent in agents:
        inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
        data = json_read(inbox_file, {})
        if not data:
            continue
        inbox = Inbox.from_dict(data)
        changed = False
        for m_raw in inbox.messages:
            content = inbox.msg_field(m_raw, "content", "")
            if not any(tag in content for tag in ROUND2_TAGS):
                continue
            state = inbox.msg_field(m_raw, "state", "") or inbox.msg_field(m_raw, "status", "")
            if state in (MsgStatus.DONE, MsgStatus.CLOSED, "done", "closed"):
                continue
            mid = inbox.msg_field(m_raw, "id", "")
            inbox.set_msg_status(
                mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                done_at=ts, done_note="auto: round2 superseded by game-stellar v2",
            )
            closed += 1
            changed = True
        if changed:
            json_write(inbox_file, inbox.to_dict())
    return closed


def clear_round2_queues(data_dir: str, agents: list[str]) -> int:
    paths = resolve_paths(data_dir)
    cleared = 0
    for base in (paths["queue_urgent"], paths["queue_normal"]):
        for agent in agents:
            qf = f"{base}/{agent}.json"
            msgs = json_read(qf, [])
            if not msgs:
                continue
            keep = [m for m in msgs if not any(t in (m.get("content") or "") for t in ROUND2_TAGS)]
            if len(keep) != len(msgs):
                json_write(qf, keep if keep else [])
                cleared += len(msgs) - len(keep)
    return cleared


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="/mailbus/store")
    args = ap.parse_args()

    from lib.commands import load_config
    cfg = load_config(os.path.join(args.data_dir, "config.json"))
    agents = list(cfg.get("agents", {}).keys())

    print("=== fix stale chains ===")
    print(f"  fixed {fix_stale_chains(args.data_dir)}")

    print("=== fix superseded task ===")
    fix_superseded_task(args.data_dir)

    print("=== close round2 inbox ===")
    print(f"  closed {close_round2_inbox(args.data_dir, agents)}")

    print("=== clear round2 queues ===")
    print(f"  cleared {clear_round2_queues(args.data_dir, agents)}")

    print("=== flush pending audits ===")
    out = reconcile_pending_audits(args.data_dir)
    print(f"  consumed={out.get('consumed',0)} backfilled={out.get('backfilled',0)}")

    from lib.audit_dispatch import list_pending_audit_tasks
    pending = len(list_pending_audit_tasks(args.data_dir, 500))
    print(f"  pending_audit={pending}")


if __name__ == "__main__":
    main()
