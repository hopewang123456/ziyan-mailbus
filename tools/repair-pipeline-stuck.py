#!/usr/bin/env python3
"""修复卡住的 pipeline 任务（mailbus 侧运维，不改 agent）。

- 取消 bus send 误建的 msg-* 重复 tracker
- 清理 stale queue/urgent/*.json
- 可选：从 queue 备份恢复 inbox pending 消息
- 报告 phantom completion（replies 有完成叙述但无 msg-results）

用法:
  python3 tools/repair-pipeline-stuck.py --task-id game-stellar-20260618
  python3 tools/repair-pipeline-stuck.py --task-id game-stellar-20260618 --fix
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utils import json_read, json_write
from lib.models import Inbox, MsgStatus
from lib.tracker import TaskTracker


def report(data_dir: str, task_id: str) -> dict:
    tr = TaskTracker(data_dir)
    task = tr.get(task_id) or {}
    mr = os.path.join(data_dir, "msg-results", f"{task_id}.json")
    out = {
        "task_id": task_id,
        "status": task.get("status"),
        "assignee": task.get("assignee"),
        "has_msg_results": os.path.isfile(mr),
        "duplicate_trackers": [],
        "stale_queues": [],
        "phantom_replies": [],
        "inbox_missing_task": False,
    }

    for t in tr.list_all():
        tid = t.get("task_id", "")
        if tid.startswith("msg-") and task_id in (t.get("summary") or ""):
            out["duplicate_trackers"].append({"task_id": tid, "status": t.get("status")})

    assignee = (task.get("chain") or [{}])[-1].get("to_person") or task.get("assignee", "")
    if assignee:
        qf = os.path.join(data_dir, "queue", "urgent", f"{assignee}.json")
        if os.path.isfile(qf):
            out["stale_queues"].append(qf)

        inbox_file = os.path.join(data_dir, "inbox", assignee, "inbox.json")
        inbox_data = json_read(inbox_file, {})
        has_task_msg = False
        if inbox_data:
            inbox = Inbox.from_dict(inbox_data)
            for m in inbox.messages:
                c = inbox.msg_field(m, "content", "")
                tid_f = inbox.msg_field(m, "task_id", "")
                if task_id in c or tid_f == task_id:
                    has_task_msg = True
                    break
        out["inbox_missing_task"] = not has_task_msg

    replies_file = os.path.join(data_dir, "replies", f"{assignee}.json")
    rep = json_read(replies_file, {})
    if rep and task_id in json.dumps(rep, ensure_ascii=False):
        if not os.path.isfile(mr):
            out["phantom_replies"].append(replies_file)

    return out


def fix(data_dir: str, task_id: str) -> None:
    tr = TaskTracker(data_dir)
    for t in tr.list_all():
        tid = t.get("task_id", "")
        if tid.startswith("msg-") and task_id in (t.get("summary") or ""):
            tr.update_status(tid, "cancelled", error={"reason": "repair: duplicate msg-* tracker"})

    task = tr.get(task_id) or {}
    assignee = (task.get("chain") or [{}])[-1].get("to_person") or task.get("assignee", "")
    if assignee:
        qf = os.path.join(data_dir, "queue", "urgent", f"{assignee}.json")
        if os.path.isfile(qf):
            os.remove(qf)
            print(f"  已删 stale queue: {qf}")

    # 清空 phantom reply 避免误判
    rf = os.path.join(data_dir, "replies", f"{assignee}.json")
    if os.path.isfile(rf) and not os.path.isfile(os.path.join(data_dir, "msg-results", f"{task_id}.json")):
        json_write(rf, {})
        print(f"  已清空 phantom reply: {rf}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="store")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    info = report(args.data_dir, args.task_id)
    print(json.dumps(info, ensure_ascii=False, indent=2))

    if args.fix:
        fix(args.data_dir, args.task_id)
        print("  ✓ repair 完成；请运行 pipeline-push-step1.py 重推 Step1")

    issues = []
    if not info["has_msg_results"]:
        issues.append("无 msg-results")
    if info["duplicate_trackers"]:
        issues.append(f"{len(info['duplicate_trackers'])} 条重复 tracker")
    if info["stale_queues"]:
        issues.append("stale queue")
    if info["phantom_replies"]:
        issues.append("phantom reply（口头完成未落盘）")
    if info["inbox_missing_task"]:
        issues.append("inbox 无 task 消息")

    if issues:
        print(f"  问题: {', '.join(issues)}")
        return 1
    print("  OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
