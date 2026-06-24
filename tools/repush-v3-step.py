#!/usr/bin/env python3
"""重置并 re-push 指定 agent 的 V3 pipeline 工单。"""
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.commands import load_config, run_scan_once
from lib.models import Inbox, MsgStatus, Priority
from lib.utils import json_read, json_write, resolve_paths

TASK_ID = "game-stellar-v3-20260617"


def repush_step(data_dir: str, agent: str, step_id: str) -> bool:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    inbox = Inbox.from_dict(json_read(inbox_file, {}))
    tag = f"【{TASK_ID}】"
    sid = step_id
    mid = None
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "")
        if tag in content and sid in content:
            mid = inbox.msg_field(m, "id", "")
            break
    if not mid:
        print(f"✗ 未找到 {agent} {step_id} 工单")
        return False
    inbox.set_msg_status(
        mid, MsgStatus.PENDING, state=MsgStatus.PENDING,
        priority=Priority.URGENT if agent == "lingxiao" else Priority.NORMAL,
        pushed_count=0, reminded_count=0,
        done_at=None, done_note=None,
        acknowledged_at=None, received_at=None, last_pushed_at=None,
    )
    json_write(inbox_file, inbox.to_dict())
    print(f"✓ {mid} → pending ({agent} {step_id})")
    return True


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--step-id", required=True)
    ap.add_argument("--no-scan", action="store_true")
    args = ap.parse_args()

    cfg = load_config(os.path.join(MAIL, "store", "config.json"))
    if not repush_step(cfg["data_dir"], args.agent, args.step_id):
        return 1
    if args.no_scan:
        return 0
    return run_scan_once(cfg["data_dir"], cfg, quiet=False)


if __name__ == "__main__":
    raise SystemExit(main())
