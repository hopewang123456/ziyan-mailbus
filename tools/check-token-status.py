#!/usr/bin/env python3
"""读取 /api/status 中的 token 活动度与 scheduler 状态。"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib.constants import DEFAULT_API_BASE

url = sys.argv[1] if len(sys.argv) > 1 else f"{DEFAULT_API_BASE}/api/status"
with urllib.request.urlopen(url, timeout=10) as resp:
    data = json.load(resp)

sched = data.get("scheduler") or {}
print("scheduler.running:", sched.get("running"))
print("scan_interval_effective:", sched.get("scan_interval_effective"))
print("token_activity:", json.dumps(sched.get("token_activity"), ensure_ascii=False, indent=2))
jobs = sched.get("jobs") or {}
for jid, st in sorted(jobs.items()):
    print(
        f"  job {jid}: last={st.get('last_run_iso')} "
        f"rc={st.get('last_rc')} elapsed={st.get('last_elapsed_s')}s"
    )
