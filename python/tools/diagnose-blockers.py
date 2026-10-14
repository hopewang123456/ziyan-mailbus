#!/usr/bin/env python3
"""mailbus 卡点诊断 — 运行中任务、stale chain、agent inbox 积压。"""
import json, os, sys, urllib.request

MAIL_API = os.environ.get("MAILBUS_URL", "http://127.0.0.1:9814")

def api_get(path):
    try:
        req = urllib.request.Request(f"{MAIL_API}{path}", headers={"User-Agent": "clinic/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

# 任务统计
stats = api_get("/api/stats")
ts = stats.get("task_statuses", {})
print("=== 任务状态分布 ===")
for k in ("running", "pending", "failed", "timeout", "cancelled", "success"):
    print(f"  {k}: {ts.get(k, 0)}")

# 任务列表 — 异常任务
tasks_r = api_get("/api/tasks?limit=50")
tasks = (tasks_r.get("tasks") or [])
broken = [t for t in tasks if t.get("status") not in ("success", "completed", "done")]
if broken:
    print(f"\n=== 异常任务 ({len(broken)}) ===")
    for t in broken:
        tid = t.get("task_id") or t.get("id", "?")
        status = t.get("status", "?")
        summary = t.get("summary") or t.get("title") or ""
        print(f"  [{status}] {tid}  {summary[:80]}")

# Agent 工作负载
workload = api_get("/api/workload")
agents = workload.get("agents", {})
busy = [(k, v) for k, v in agents.items() if v.get("inbox_pending", 0) > 0]
if busy:
    print(f"\n=== Agent Inbox 积压 ({len(busy)}) ===")
    for aid, a in busy:
        print(f"  {a.get('name', aid)}: pending={a.get('inbox_pending', 0)} active_tasks={a.get('active_tasks', 0)}")

# Doctor 卡点
doctor = api_get("/api/doctor")
issues = [i for i in (doctor.get("items") or []) if i.get("level") == "fail"]
if issues:
    print(f"\n=== Doctor FAIL ({len(issues)}) ===")
    for i in issues:
        print(f"  [{i.get('category')}] {i.get('message')}: {i.get('detail', '')}")

if not broken and not busy and not issues:
    print("\n  No blockers detected — all clear.")
