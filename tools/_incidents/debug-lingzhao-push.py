#!/usr/bin/env python3
"""Diagnose why lingzhao pipeline msg is not pushed."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.commands import load_config
from lib.models import Inbox
from lib.scanner import (
    _agent_has_active_work,
    _get_running_pipeline_task_ids,
    _has_pushed_message,
    build_queues,
    pipeline_inbox_message_stale,
    scan_all,
    should_skip_push,
)
from lib.utils import json_read, resolve_paths

TASK_ID = "game-courier-20260625"
MSG_ID = "msg-20260625-59463"
AGENT = "lingzhao"


def main() -> int:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
    cfg = load_config(os.path.join(data_dir, "config.json"))
    agents = cfg.get("agents", {})
    paths = resolve_paths(data_dir)

    print("=== pipeline_ids ===")
    print(_get_running_pipeline_task_ids(data_dir, AGENT))

    inbox_data = json_read(os.path.join(paths["inbox"], AGENT, "inbox.json"), {})
    inbox = Inbox.from_dict(inbox_data)
    print("\n=== inbox constraints ===")
    print("has_pushed:", _has_pushed_message(inbox))
    print("has_active_work:", _agent_has_active_work(inbox, data_dir, AGENT, agents))

    print("\n=== game-courier messages ===")
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "") or ""
        if TASK_ID not in content and inbox.msg_field(m, "id", "") != MSG_ID:
            continue
        mid = inbox.msg_field(m, "id", "")
        d = m if isinstance(m, dict) else (m.to_dict() if hasattr(m, "to_dict") else {})
        if not isinstance(d, dict):
            d = {"id": mid, "content": content}
        state = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")
        print(f"  id={mid} state={state} type={inbox.msg_field(m,'type','')} priority={inbox.msg_field(m,'priority','')}")
        print(f"  pushed_count={inbox.msg_field(m,'pushed_count',0)} last_pushed_at={inbox.msg_field(m,'last_pushed_at','')}")
        print(f"  skip_push={should_skip_push(data_dir, d if isinstance(d,dict) and 'id' in d else inbox.get_msg(mid).to_dict() if hasattr(inbox.get_msg(mid),'to_dict') else d, cfg)}")
        print(f"  stale={pipeline_inbox_message_stale(data_dir, AGENT, content)}")

    print("\n=== active inbox (non-done) ===")
    for m in inbox.messages:
        state = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if state in ("done", "closed", "archived"):
            continue
        mid = inbox.msg_field(m, "id", "")
        print(f"  {mid[:40]} state={state} type={inbox.msg_field(m,'type','')} pushed={inbox.msg_field(m,'pushed_count',0)}")

    uq, nq = build_queues(data_dir, agents, cfg)
    print("\n=== build_queues ===")
    print("lingzhao urgent:", len(uq.get(AGENT, [])))
    print("lingzhao normal:", len(nq.get(AGENT, [])))

    for name, urgent, normal in scan_all(data_dir, agents):
        if name != AGENT:
            continue
        print(f"scan_all urgent={len(urgent)} normal={len(normal)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
