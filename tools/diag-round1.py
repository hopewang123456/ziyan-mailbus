#!/usr/bin/env python3
"""Diagnose Round1 pipeline push blocking."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.scanner import build_queues, _has_pushed_message, get_msg_state, scan_all
from lib.models import MsgStatus
from lib.utils import resolve_paths, json_read
from lib.models import Inbox

DATA_DIR = os.environ.get("MAILBUS_DATA", "store")


def main():
    paths = resolve_paths(DATA_DIR)
    inbox_file = f"{paths['inbox']}/lingzhao/inbox.json"
    inbox_data = json_read(inbox_file, {})
    inbox = Inbox.from_dict(inbox_data)

    pushed_status = []
    pushed_state = []
    processing = []
    pending_task = []
    pending_urgent = []
    hardening = []

    for m in inbox.messages:
        mid = m.id if hasattr(m, "id") else m.get("id")
        state = get_msg_state(m)
        mtype = m.type if hasattr(m, "type") else m.get("type")
        pri = m.priority if hasattr(m, "priority") else m.get("priority")
        content = (m.content if hasattr(m, "content") else m.get("content", ""))[:60]

        if state == MsgStatus.PUSHED:
            pushed_state.append(mid)
        raw = m.to_dict() if hasattr(m, "to_dict") else m
        if raw.get("status") == MsgStatus.PUSHED:
            pushed_status.append(mid)
        if state == MsgStatus.PROCESSING:
            processing.append((mid, mtype, content))
        if state == MsgStatus.PENDING and mtype == "task":
            pending_task.append((mid, pri, content))
        if state == MsgStatus.PENDING and pri == "urgent":
            pending_urgent.append((mid, mtype, content))
        if "mailbus-hardening" in (m.content if hasattr(m, "content") else m.get("content", "")):
            hardening.append((mid, state, mtype, pri))

    print("=== lingzhao inbox diagnosis ===")
    print(f"total messages: {len(inbox.messages)}")
    print(f"_has_pushed_message: {_has_pushed_message(inbox)}")
    print(f"status=pushed (legacy): {pushed_status[:5]} count={len(pushed_status)}")
    print(f"state=pushed: {pushed_state[:5]} count={len(pushed_state)}")
    print(f"processing ({len(processing)}):")
    for row in processing[:8]:
        print(f"  {row}")
    print(f"pending task ({len(pending_task)}):")
    for row in pending_task[:5]:
        print(f"  {row}")
    print(f"pending urgent head ({len(pending_urgent)}):")
    for row in pending_urgent[:5]:
        print(f"  {row}")
    print(f"hardening msgs:")
    for row in hardening:
        print(f"  {row}")

    config = json_read(os.path.join(DATA_DIR, "config.json"), {})
    agents = config.get("agents", {})
    scanned = scan_all(DATA_DIR, agents)
    for name, u, n in scanned:
        if name == "lingzhao":
            print(f"\nscan_all lingzhao: urgent={len(u)} normal={len(n)}")
            if u:
                print(f"  urgent head: {u[0].id} type={u[0].type} pri={u[0].priority}")
            if n:
                print(f"  normal head: {n[0].id} type={n[0].type} pri={n[0].priority}")

    uq, nq = build_queues(DATA_DIR, agents)
    print(f"\nbuild_queues: urgent agents={list(uq.keys())} normal agents={list(nq.keys())}")
    if "lingzhao" in uq:
        print(f"  lingzhao urgent queue: {uq['lingzhao'][0].id}")
    elif "lingzhao" in nq:
        print(f"  lingzhao normal queue: {nq['lingzhao'][0].id}")
    else:
        print("  lingzhao NOT in queues!")


if __name__ == "__main__":
    main()
