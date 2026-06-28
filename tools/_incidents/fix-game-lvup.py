#!/usr/bin/env python3
"""回收灵昭 game-lvup 回复 → msg-results，取消重复 smoke 任务，推进 pipeline。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utils import json_read, json_write, resolve_paths, _now_iso
from lib.models import Inbox, MsgStatus
from lib.tracker import TaskTracker

DATA_DIR = os.environ.get("MAILBUS_DATA", "store")
PRIMARY = "game-lvup-20260615-171754"
DUPLICATE = "game-lvup-20260615-171010"
MSG_ID = "msg-20260615-75122"

SUMMARY = (
    "打怪升级小游戏 MVP 方案三点："
    "1) 回合制战斗闭环(攻击/防御/技能)；"
    "2) Lv1-10 数值成长+怪物分区+装备掉落；"
    "3) 终端或单页HTML三面板(状态/日志/背包)，HTML+JS+localStorage。"
)


def write_msg_results(data_dir: str) -> str:
    path = os.path.join(data_dir, "msg-results", f"{PRIMARY}.json")
    payload = {
        "template": "report",
        "conclusion": "done",
        "task": PRIMARY,
        "summary": SUMMARY,
        "next_role": "调度员",
        "result": {
            "message": "game-lvup MVP plan — recovered from lingzhao reply",
            "deliverables": [f"msg-results/{PRIMARY}.json"],
        },
        "source": "recovered-from-lingzhao-reply",
        "msg_id": MSG_ID,
        "agent": "lingzhao",
        "timestamp": _now_iso(),
    }
    json_write(path, payload)
    return path


def mark_msg_done(data_dir: str) -> bool:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/lingzhao/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return False
    inbox = Inbox.from_dict(inbox_data)
    ts = _now_iso()
    ok = inbox.set_msg_status(
        MSG_ID,
        MsgStatus.ACKNOWLEDGED,
        state=MsgStatus.DONE,
        done_at=ts,
        done_note=f"msg-results/{PRIMARY}.json recovered",
        acknowledged_at=ts,
    )
    if ok:
        json_write(inbox_file, inbox.to_dict())
    return ok


def cancel_duplicate(data_dir: str) -> None:
    tr = TaskTracker(data_dir)
    t = tr.get(DUPLICATE)
    if not t:
        return
    t["status"] = "cancelled"
    t["error"] = "duplicate smoke-test task; use game-lvup-20260615-171754"
    for step in t.get("chain", []):
        if step.get("status") == "running":
            step["status"] = "cancelled"
            step["completed_at"] = _now_iso()
    task_file = os.path.join(tr.tasks_dir, f"{DUPLICATE}.json")
    json_write(task_file, t)


def main():
    path = write_msg_results(DATA_DIR)
    print(f"wrote {path}")
    print(f"mark msg done: {mark_msg_done(DATA_DIR)}")
    cancel_duplicate(DATA_DIR)
    print(f"cancelled duplicate {DUPLICATE}")


if __name__ == "__main__":
    main()
