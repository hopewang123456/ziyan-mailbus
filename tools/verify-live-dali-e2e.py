#!/usr/bin/env python3
"""Verify an existing live dali E2E task (post-hoc gate check)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

TZ_CN = timezone(timedelta(hours=8))
MAIL_ROOT = os.environ.get("MAILBUS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, MAIL_ROOT)

from lib.file_task_push import verify_file_task_delivery
from lib.task_fsm import read_step_result
from lib.utils import json_read


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="store")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--step-id", default="s1")
    args = ap.parse_args()
    data_dir = os.path.abspath(os.path.join(MAIL_ROOT, args.data_dir))
    tid, sid = args.task_id, args.step_id
    path = os.path.join(data_dir, "msg-results", tid, f"step-{sid}.json")
    if not os.path.isfile(path):
        print(f"FAIL missing {path}")
        return 1
    result = json_read(path, {})
    status = (result.get("status") or result.get("conclusion") or "").lower()
    if status not in ("done", "pass", "submitted", "ok"):
        print(f"FAIL bad status: {result}")
        return 1
    task = json_read(os.path.join(data_dir, "tasks", f"{tid}.json"), {})
    chain = task.get("chain") or []
    step = next((s for s in chain if (s.get("step_id") or "") == sid), chain[0] if chain else {"step_id": sid})
    if not read_step_result(data_dir, tid, step):
        print("FAIL FSM cannot read step result")
        return 1
    deliverable = os.path.join(data_dir, "deliverables", tid, "P5_LIVE_OK.txt")
    if not os.path.isfile(deliverable):
        print(f"WARN missing deliverable {deliverable}")
    inbox = json_read(os.path.join(data_dir, "inbox", "dali", "inbox.json"), {})
    for m in inbox.get("messages") or []:
        if m.get("task_id") != tid:
            continue
        ok, reason = verify_file_task_delivery(data_dir, "dali", m, reply_text=m.get("reply_text") or "")
        if not ok and reason == "phantom_reply_text":
            print("FAIL phantom gate")
            return 1
    report = {
        "task_id": tid,
        "verified_at": datetime.now(TZ_CN).isoformat(),
        "step_result": path,
        "summary": result.get("summary", ""),
        "live_opencode": True,
    }
    out = os.path.join(data_dir, "msg-results", f"{tid}-live-e2e.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"PASS {tid} report={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
