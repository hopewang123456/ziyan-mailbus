#!/usr/bin/env python3
"""Re-pin active pipeline step to a different agent (manual or failover helper)."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.dispatch.pipeline_step_failover import failover_pipeline_step
from lib.models import Inbox, MsgStatus
from lib.pipeline_trigger import _send_task
from lib.task_fsm import get_active_step, read_step_result
from lib.tracker import TaskTracker
from lib.utils import json_read, json_write, resolve_paths, _now_iso


def _close_inbox_msgs(data_dir: str, agent: str, task_id: str) -> int:
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], agent, "inbox.json")
    if not os.path.isfile(inbox_file):
        return 0
    inbox = Inbox.from_dict(json_read(inbox_file, {}))
    closed = 0
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "") or ""
        if task_id not in content and inbox.msg_field(m, "task_id", "") != task_id:
            continue
        mid = inbox.msg_field(m, "id", "")
        state = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if state in ("done", "closed", "archived"):
            continue
        inbox.set_msg_status(mid, MsgStatus.CLOSED, state=MsgStatus.CLOSED)
        closed += 1
        print(f"closed {agent} {mid} ({state})")
    if closed:
        json_write(inbox_file, inbox.to_dict())
    return closed


def manual_reassign(data_dir: str, task_id: str, new_agent: str, old_agent: str | None) -> int:
    tr = TaskTracker(data_dir)
    task = tr.get(task_id) or {}
    step = get_active_step(task) or {}
    if not step:
        print("no active step")
        return 1

    step_num = step.get("step") or 0
    step_id = step.get("step_id") or f"s{step_num}"
    prev_agent = old_agent or step.get("to_agent") or step.get("to_person") or ""
    print(f"re-pin step {step_num} ({step_id}): {prev_agent} -> {new_agent}")

    for s in task.get("chain") or []:
        if s.get("step") != step_num:
            continue
        s["pin_agent"] = new_agent
        s["to_agent"] = new_agent
        s["to_person"] = new_agent
        s["dispatch_meta"] = {
            "method": "manual_reassign",
            "reason": f"manual->{new_agent}",
            "reassigned_at": _now_iso(),
            "from_agent": prev_agent,
        }

    task["assignee"] = new_agent
    task["updated_at"] = _now_iso()
    json_write(os.path.join(tr.tasks_dir, f"{task_id}.json"), task)

    if prev_agent:
        _close_inbox_msgs(data_dir, prev_agent, task_id)

    paths = resolve_paths(data_dir)
    prev = read_step_result(data_dir, task_id, {"step_id": f"s{max(int(step_num) - 1, 1)}"})
    summary = (
        (prev or {}).get("summary")
        or step.get("summary")
        or f"继续 {task_id} pipeline step {step_num}。"
    )
    ok = _send_task(
        data_dir,
        paths,
        from_person=step.get("from_agent") or "mailbus",
        from_role=step.get("from_role") or "",
        to_role=step.get("to_role") or "",
        to_person=new_agent,
        summary=summary,
        task_id=task_id,
        step_num=step_num,
        step_id=step_id,
        result_ref=step.get("result_ref"),
    )
    if not ok:
        print("send_task failed")
        return 1
    print(f"inbox message created for {new_agent}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-pin active pipeline step to another agent")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--agent", help="Target agent (manual pin)")
    parser.add_argument("--from-agent", help="Close inbox on this agent (default: current assignee)")
    parser.add_argument(
        "--failover", action="store_true",
        help="按工种 failover：同工种 → 相近工种（见 pipeline_ops.role_failover）",
    )
    args = parser.parse_args()

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
    if args.failover:
        new_agent = failover_pipeline_step(
            data_dir, args.task_id, reason="manual_failover_cli",
            from_agent=args.from_agent,
        )
        if not new_agent:
            print("failover: no candidate available")
            return 1
        print(f"failover -> {new_agent}")
        return 0
    if not args.agent:
        parser.error("--agent or --failover required")
    return manual_reassign(data_dir, args.task_id, args.agent, args.from_agent)


if __name__ == "__main__":
    raise SystemExit(main())
