#!/usr/bin/env python3
"""Token / Scan 状态 — 检查 scheduler 状态与 token 活动级别。"""
import json, os, sys, urllib.request

MAIL_API = os.environ.get("MAILBUS_URL", "http://127.0.0.1:9814")

def api_get(path):
    try:
        req = urllib.request.Request(f"{MAIL_API}{path}", headers={"User-Agent": "clinic/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

status = api_get("/api/status")
scheduler = status.get("scheduler", {})
token = status.get("token_activity", scheduler.get("token_activity", {}))

print(f"bus: {status.get('status', '?')}  version={status.get('version', '?')}")
print(f"scheduler: {'running' if scheduler.get('running') else 'stopped'}")
print(f"scan interval: {scheduler.get('scan_interval_effective', '?')}s")

jobs = scheduler.get("jobs", {})
print(f"\njobs ({len(jobs)}):")
for name, j in sorted(jobs.items()):
    rc = j.get("last_rc", "?")
    last = j.get("last_run_iso", "-")
    elapsed = j.get("last_elapsed_s", 0)
    mark = "OK" if rc == 0 else f"FAIL(rc={rc})"
    print(f"  [{mark}] {name:30s}  {last}  {elapsed:.1f}s")

ta = status.get("token_activity") or token
if ta:
    print(f"\ntoken_activity: {ta.get('level', '?')}")
    print(f"  pending={ta.get('pending_messages', 0)} processing={ta.get('processing', 0)}")
    print(f"  running_tasks={ta.get('running_tasks', 0)} high_priority={ta.get('high_priority_tasks', 0)}")

gate = status.get("round1_gate", {})
if gate and not gate.get("round1_passed"):
    print(f"\nROUND1 GATE: NOT PASSED")
    for b in gate.get("blockers", []):
        print(f"  - {b}")
