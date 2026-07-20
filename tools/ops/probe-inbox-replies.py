#!/usr/bin/env python3
"""Probe inbox/replies/tasks for agent message flow."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("MAILBUS_URL", "http://127.0.0.1:9814").rstrip("/")
AGENTS = ("lingxi", "lingyun", "lingzhao")


def fetch(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    print(f"BASE={BASE}\n")
    for agent in AGENTS:
        try:
            inbox = fetch(f"/api/inbox/{agent}?limit=30")
        except Exception as exc:
            print(f"INBOX {agent}: ERROR {exc}")
            continue
        msgs = inbox.get("messages") or []
        print(f"=== inbox/{agent} unread={inbox.get('has_unread')} count={len(msgs)} ===")
        for m in msgs[:8]:
            mid = (m.get("id") or "?")[:20]
            print(
                f"  {mid} type={m.get('type')} from={m.get('from')} to={m.get('to')} "
                f"status={m.get('status', m.get('state', ''))} "
                f"subject={(m.get('subject') or m.get('content') or '')[:50]!r}"
            )

    try:
        replies = fetch("/api/replies?limit=50")
        items = replies.get("replies") or replies.get("items") or []
        print(f"\n=== replies (recent {len(items)}) ===")
        for r in items[:15]:
            if any(a in str(r) for a in AGENTS):
                print(
                    f"  from={r.get('from_agent', r.get('from'))} to={r.get('to_agent', r.get('to'))} "
                    f"task={str(r.get('task_id', r.get('in_reply_to', '')))[:16]} "
                    f"{(r.get('summary') or r.get('content') or '')[:60]!r}"
                )
    except Exception as exc:
        print(f"\nreplies ERROR: {exc}")

    try:
        tasks = fetch("/api/tasks?limit=80")
        tlist = tasks.get("tasks") or tasks.get("items") or []
        print(f"\n=== tasks mentioning lingxi/lingyun/lingzhao ({len(tlist)} total scanned) ===")
        for t in tlist:
            blob = json.dumps(t, ensure_ascii=False)
            if not any(a in blob for a in AGENTS):
                continue
            print(
                f"  id={str(t.get('id', ''))[:18]} status={t.get('status')} "
                f"assignee={t.get('assignee', t.get('to', ''))} "
                f"from={t.get('from', t.get('initiator', ''))} "
                f"{(t.get('subject') or t.get('title') or t.get('content') or '')[:55]!r}"
            )
    except Exception as exc:
        print(f"\ntasks ERROR: {exc}")

    try:
        status = fetch("/api/status")
        sched = status.get("scheduler") or {}
        print(f"\n=== scheduler ===")
        print(f"  enabled={sched.get('enabled')} jobs={len(sched.get('jobs') or [])}")
        for j in (sched.get("jobs") or [])[:8]:
            print(f"  - {j.get('id')}: last={j.get('last_run')} ok={j.get('last_ok')}")
    except Exception as exc:
        print(f"\nstatus ERROR: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
