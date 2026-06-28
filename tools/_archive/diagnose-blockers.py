#!/usr/bin/env python3
"""mailbus 卡点诊断 — pending/processing/running 任务汇总"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox
from lib.tracker import TaskTracker
from lib.utils import json_read, resolve_paths

DATA = "/mailbus/store"
paths = resolve_paths(DATA)

print("=== RUNNING TASKS (top 15) ===")
running = [t for t in TaskTracker(DATA).list_all() if t.get("status") == "running"]
running.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
for t in running[:15]:
    ch = t.get("chain") or []
    cur = ch[-1] if ch else {}
    print(f"  {t.get('task_id','?')[:40]:40} assignee={t.get('assignee','?'):10} step={cur.get('to_person','?')} state={cur.get('status','?')}")

print(f"\n  total running: {len(running)}")

print("=== STALE TASK JSON (task=success but chain step=running) ===")
stale = 0
for t in TaskTracker(DATA).list_all():
    if t.get("status") in ("success", "cancelled", "failed"):
        ch = t.get("chain") or []
        if ch and ch[-1].get("status") == "running":
            stale += 1
            print(f"  {t.get('task_id','?')[:45]} task={t.get('status')} chain_step=running")
print(f"  total stale chain: {stale}")

print("\n=== INBOX BLOCKERS (pending/pushed/processing) ===")
from lib.commands import load_config
cfg = load_config(f"{DATA}/config.json")
agent_names = list(cfg.get("agents", {}).keys())

for agent in agent_names:
    f = f"{paths['inbox']}/{agent}/inbox.json"
    d = json_read(f, {})
    if not d:
        continue
    inbox = Inbox.from_dict(d)
    blockers = []
    for m in inbox.messages:
        st = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")
        if st in ("pending", "pushed", "processing"):
            mid = inbox.msg_field(m, "id", "")
            content = (inbox.msg_field(m, "content", "") or "")[:70].replace("\n", " ")
            blockers.append((st, mid, content))
    if blockers:
        print(f"\n  [{agent}] {len(blockers)} active")
        for st, mid, c in blockers[:5]:
            print(f"    {st:12} {mid} {c}")
        if len(blockers) > 5:
            print(f"    ... +{len(blockers)-5} more")

print("\n=== PRIMARY TASK ===")
ist = json_read(f"{DATA}/iterations/iteration-state.json", {})
print(f"  primary={ist.get('primary_task_id')} status={ist.get('gate',{}).get('primary_status')} blockers={ist.get('gate',{}).get('blockers')}")
