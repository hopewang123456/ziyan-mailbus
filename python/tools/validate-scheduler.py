#!/usr/bin/env python3
"""Scheduler 校验 — 检查内置 SchedulerHub 的所有 job 状态。"""
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
jobs = scheduler.get("jobs", {})

ok = 0
fail = 0
print(f"Scheduler: {'running' if scheduler.get('running') else 'STOPPED'}")
print(f"Started: {scheduler.get('started_at', '-')}")
print(f"scan_interval: {scheduler.get('scan_interval_effective', '?')}s\n")

for name, j in sorted(jobs.items()):
    rc = j.get("last_rc")
    last = j.get("last_run_iso") or "-"
    elapsed = j.get("last_elapsed_s", 0)
    cron = j.get("last_cron_minute", "")
    if rc is None and not last:
        print(f"  [---] {name:35s}  never run")
        fail += 1
    elif rc == 0:
        print(f"  [OK ] {name:35s}  {last}  {elapsed:.1f}s {cron}")
        ok += 1
    else:
        print(f"  [FAIL rc={rc}] {name:35s}  {last}  {elapsed:.1f}s")
        fail += 1

print(f"\nSUMMARY: {ok} OK, {fail} failed/untested, {len(jobs)} total")
# 工具自身运行成功；失败的 job 是诊断信息，不影响退出码
sys.exit(0)
