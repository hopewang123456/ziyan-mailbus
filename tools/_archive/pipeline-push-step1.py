#!/usr/bin/env python3
"""Pipeline Step1 推送 — 结构化工单 + API send-msg（不触发 bus send 重复 tracker）。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.pipeline_work_order import write_pipeline_work_order
from lib.tracker import TaskTracker
from lib.pipeline_chain import agent_to_role


API = os.environ.get("MAILBUS_API", "http://127.0.0.1:9814")


def cancel_duplicate_trackers(data_dir: str, pipeline_task_id: str) -> int:
    tr = TaskTracker(data_dir)
    n = 0
    for t in tr.list_all():
        tid = t.get("task_id", "")
        if not tid.startswith("msg-"):
            continue
        if pipeline_task_id in (t.get("summary") or ""):
            tr.update_status(tid, "cancelled", error={"reason": "duplicate: use pipeline task_id only"})
            n += 1
    return n


def push_via_api(to: str, content: str, task_id: str, *, priority: str = "urgent", api: str = API) -> str:
    payload = {
        "to": to,
        "from": "mailbus",
        "content": content,
        "type": "task",
        "priority": priority,
        "task_id": task_id,
    }
    req = urllib.request.Request(
        f"{api}/api/send-msg",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("msg_id", "?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "store"))
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--api", default=API)
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    tr = TaskTracker(args.data_dir)
    task = tr.get(args.task_id)
    if not task:
        print(f"error: task not found: {args.task_id}", file=sys.stderr)
        return 1

    n = cancel_duplicate_trackers(args.data_dir, args.task_id)
    if n:
        print(f"cancelled duplicate trackers: {n}", file=sys.stderr)

    chain = task.get("chain") or []
    cur = chain[-1] if chain else {}
    step = cur.get("step") or 1
    role = cur.get("to_role") or agent_to_role(args.agent)
    head = chain[0] if chain else {}
    planned_rt = head.get("planned_role_types")
    planned = head.get("planned_agents") if not planned_rt else None

    _, wo_path = write_pipeline_work_order(
        args.data_dir,
        task_id=args.task_id,
        step_num=step,
        to_person=args.agent,
        to_role=role,
        summary=task.get("intent") or task.get("summary", ""),
        planned_agents=planned,
        planned_role_types=planned_rt,
    )

    content = (
        f"【{args.task_id}】Pipeline Step{step}\n\n"
        f"task_id: {args.task_id}\n"
        f"工单: {wo_path}\n"
        f"结果: store/msg-results/{args.task_id}.json\n"
        f"规范: store/rules/pipeline-agent-paths.md\n"
    )

    if args.no_push:
        print(f"work_order: {wo_path}")
        return 0

    api_msg_id = push_via_api(args.agent, content, args.task_id, priority="urgent", api=args.api)
    print(f"msg_id={api_msg_id} work_order={wo_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
