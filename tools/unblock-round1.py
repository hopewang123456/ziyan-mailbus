#!/usr/bin/env python3
"""一次性解除 Round1 pipeline 阻塞：回收僵尸消息、清理队列、提升 hardening 优先级。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.scanner import recover_inbox_stale_states, build_queues
from lib.utils import json_read, json_write, resolve_paths, _now_iso
from lib.models import Inbox, Priority, MsgStatus

TASK_ID = "mailbus-hardening-20260616"
DUPLICATE_MSG = "msg-20260615-66049"
PRIMARY_MSG = "msg-20260615-04794"
DATA_DIR = os.environ.get("MAILBUS_DATA", "store")


def dedupe_hardening_messages(data_dir: str):
    """关闭重复 hardening 消息，只保留 PRIMARY_MSG 待推"""
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/lingzhao/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return 0
    inbox = Inbox.from_dict(inbox_data)
    changed = 0
    ts = _now_iso()
    for mid in (DUPLICATE_MSG,):
        if inbox.set_msg_status(
            mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
            done_at=ts, done_note="duplicate hardening task",
            acknowledged_at=ts, received_at=ts,
        ):
            changed += 1
    if inbox.set_msg_status(
        PRIMARY_MSG, "pending", state="pending", priority=Priority.URGENT,
        acknowledged_at=None, received_at=None, pushed_count=0,
    ):
        changed += 1
    if changed:
        json_write(inbox_file, inbox.to_dict())
    return changed


def kill_stale_hermes_chats():
    """清理无 --profile 的僵尸 hermes chat（错误推送模板遗留）"""
    import subprocess
    try:
        subprocess.run(
            [
                "docker", "exec", "docker-agents-hermes-1", "bash", "-c",
                "ps aux | grep 'hermes chat -q' | grep -v 'profile' | grep -v grep | awk '{print $2}' | xargs -r kill 2>/dev/null; true",
            ],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass


def bump_hardening_messages(data_dir: str):
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/lingzhao/inbox.json"
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return 0
    inbox = Inbox.from_dict(inbox_data)
    changed = 0
    for m_raw in inbox.messages:
        content = inbox.msg_field(m_raw, "content", "")
        if TASK_ID not in content:
            continue
        mid = inbox.msg_field(m_raw, "id", "")
        if mid != PRIMARY_MSG:
            continue
        if isinstance(m_raw, dict):
            m_raw["priority"] = Priority.URGENT
            m_raw["state"] = "pending"
            m_raw["status"] = "pending"
            m_raw["acknowledged_at"] = None
            m_raw["received_at"] = None
            m_raw["pushed_count"] = 0
            changed += 1
        elif inbox.set_msg_status(
            mid, "pending", state="pending", priority=Priority.URGENT,
            acknowledged_at=None, received_at=None, pushed_count=0,
        ):
            changed += 1
    if changed:
        json_write(inbox_file, inbox.to_dict())
    return changed


def clear_agent_queues(data_dir: str, agent: str):
    paths = resolve_paths(data_dir)
    for sub in ("queue_urgent", "queue_normal"):
        qf = f"{paths[sub]}/{agent}.json"
        if os.path.exists(qf):
            json_write(qf, [])


def main():
    config_path = os.path.join(DATA_DIR, "config.json")
    config = json_read(config_path, {})
    agents = config.get("agents", {})

    print("=== unblock Round1 pipeline ===")
    kill_stale_hermes_chats()
    stats = recover_inbox_stale_states(DATA_DIR, agents)
    print(f"recover: {stats}")

    deduped = dedupe_hardening_messages(DATA_DIR)
    print(f"dedupe hardening msgs: {deduped}")

    bumped = bump_hardening_messages(DATA_DIR)
    print(f"bump hardening task msgs: {bumped}")

    clear_agent_queues(DATA_DIR, "lingzhao")
    print("cleared lingzhao queue files")

    uq, nq = build_queues(DATA_DIR, agents)
    print(f"queues after fix: urgent={list(uq.keys())} normal={list(nq.keys())}")
    if "lingzhao" in uq:
        print(f"  lingzhao urgent head: {uq['lingzhao'][0].id}")
    elif "lingzhao" in nq:
        print(f"  lingzhao normal head: {nq['lingzhao'][0].id}")
    else:
        print("  WARNING: lingzhao still not queued")


if __name__ == "__main__":
    main()
