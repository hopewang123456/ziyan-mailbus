#!/usr/bin/env python3
"""打印 V3 任务 FSM 摘要与 Step5 就绪检查。"""
import json
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

TASK_ID = "game-stellar-v3-20260617"
DATA_DIR = os.path.join(MAIL, "store")


def main():
    from lib.task_fsm import ensure_fsm, fsm_summary, get_active_step
    from lib.tracker import TaskTracker
    from lib.utils import json_read, resolve_paths

    tracker = TaskTracker(DATA_DIR)
    task = tracker.get(TASK_ID)
    if not task:
        print("NOT_FOUND")
        return 1

    ensure_fsm(task)
    active = get_active_step(task)
    print("status:", task.get("status"))
    print("fsm:", json.dumps(fsm_summary(task), ensure_ascii=False, indent=2))
    if active:
        print("active_step:", json.dumps({
            "step_id": active.get("step_id"),
            "step": active.get("step"),
            "to_agent": active.get("to_agent") or active.get("to_person"),
            "role_type": active.get("role_type"),
            "to_role": active.get("to_role"),
            "fsm_state": active.get("fsm_state"),
            "status": active.get("status"),
            "result_ref": active.get("result_ref"),
        }, ensure_ascii=False, indent=2))

    paths = resolve_paths(DATA_DIR)
    sid = (active or {}).get("step_id", "s5")
    step_path = os.path.join(DATA_DIR, "msg-results", TASK_ID, f"step-{sid}.json")
    legacy = os.path.join(DATA_DIR, "msg-results", f"{TASK_ID}.json")
    print("step_result_exists:", os.path.isfile(step_path), step_path)
    print("legacy_result:", os.path.isfile(legacy))
    if os.path.isfile(legacy):
        lr = json_read(legacy, {})
        print("legacy_agent:", lr.get("agent"), "step:", lr.get("pipeline_step"))

    assignee = (active or {}).get("to_agent") or (active or {}).get("to_person") or task.get("assignee")
    if assignee:
        inbox = json_read(f"{paths['inbox']}/{assignee}/inbox.json", {}, ttl=0)
        hits = [
            m for m in inbox.get("messages", [])
            if TASK_ID in (m.get("content") or "") and (m.get("state") or m.get("status", "")).lower()
            not in ("done", "closed", "archived")
        ]
        print(f"inbox_{assignee}_active_msgs:", len(hits))
        for m in hits[:3]:
            print(" ", m.get("id"), m.get("state") or m.get("status"), (m.get("content") or "")[:60])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
