#!/usr/bin/env python3
"""Diagnose push for any agent on game-courier pipeline."""
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
    should_skip_push,
)
from lib.task_fsm import get_active_step
from lib.tracker import TaskTracker
from lib.utils import json_read, resolve_paths

TASK_ID = "game-courier-20260625"


def main() -> int:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
    cfg = load_config(os.path.join(data_dir, "config.json"))
    agents = cfg.get("agents", {})
    paths = resolve_paths(data_dir)

    t = TaskTracker(data_dir).get(TASK_ID) or {}
    step = get_active_step(t) or {}
    agent = step.get("to_agent") or step.get("to_person") or t.get("assignee") or "?"
    print(f"task={TASK_ID} status={t.get('status')} step={step.get('step')} agent={agent} fsm={step.get('fsm_state')}")

    step_dir = os.path.join(data_dir, "msg-results", TASK_ID)
    if os.path.isdir(step_dir):
        print("step_results:", sorted(os.listdir(step_dir)))

    if agent == "?":
        return 1

    print(f"pipeline_ids[{agent}]:", _get_running_pipeline_task_ids(data_dir, agent))
    inbox = Inbox.from_dict(json_read(os.path.join(paths["inbox"], agent, "inbox.json"), {}))
    print(f"has_pushed={_has_pushed_message(inbox)} active={_agent_has_active_work(inbox, data_dir, agent, agents)}")

    print(f"\n=== {agent} game-courier msgs ===")
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "") or ""
        if TASK_ID not in content:
            continue
        mid = inbox.msg_field(m, "id", "")
        d = m if isinstance(m, dict) else inbox.get_msg(mid).to_dict()
        print(f"  {mid} state={inbox.msg_field(m,'state','')} pushed={inbox.msg_field(m,'pushed_count',0)} skip={should_skip_push(data_dir, d, cfg)}")

    print("\n=== non-done inbox ===")
    for m in inbox.messages:
        st = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if st in ("done", "closed", "archived"):
            continue
        print(f"  {inbox.msg_field(m,'id','')[:36]} state={st} type={inbox.msg_field(m,'type','')}")

    uq, nq = build_queues(data_dir, agents, cfg)
    print(f"\nqueue urgent={len(uq.get(agent,[]))} normal={len(nq.get(agent,[]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
