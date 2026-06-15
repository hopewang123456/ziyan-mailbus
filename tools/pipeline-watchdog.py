#!/usr/bin/env python3
"""Pipeline 执行监控 — 异常检测、顺序编排、状态报告。

用法:
  python3 tools/pipeline-watchdog.py              # 报告 + 自动修复
  python3 tools/pipeline-watchdog.py --no-fix       # 只读报告
  python3 tools/pipeline-watchdog.py --loop 12 60   # 每 60s 监控 12 轮
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utils import json_read
from lib.tracker import TaskTracker
from lib.iteration_engine import evaluate_round1_gate
from lib.execution_orchestrator import run_orchestrator, detect_anomalies
from lib.self_heal import run_self_heal


DATA = os.environ.get("MAILBUS_DATA", "store")
SEVERITY_ICON = {"critical": "🔴", "warn": "⚠️", "info": "ℹ️"}


def _scheduler_snapshot() -> dict:
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9812/api/status", timeout=5) as r:
            return json.loads(r.read()).get("scheduler") or {}
    except Exception:
        return {}


def _running_summary(data_dir: str) -> list:
    tr = TaskTracker(data_dir)
    rows = []
    for t in tr.list_all():
        if t.get("status") != "running":
            continue
        tid = t.get("task_id", "")
        if tid.startswith(("remind-", "patrol-", "heartbeat-")):
            continue
        chain = t.get("chain") or []
        step = chain[-1] if chain else {}
        rows.append({
            "task_id": tid,
            "assignee": step.get("to_person") or t.get("assignee"),
            "role": step.get("to_role"),
            "has_result": os.path.exists(os.path.join(data_dir, "msg-results", f"{tid}.json")),
        })
    return rows


def print_report(data_dir: str, agents: dict, orch: dict):
    primary = json_read(os.path.join(data_dir, "iterations", "iteration-state.json"), {}).get("primary_task_id", "?")
    gate = evaluate_round1_gate(data_dir, agents)
    sched = _scheduler_snapshot()
    scan = (sched.get("jobs") or {}).get("scan") or {}

    print(f"\n{'='*60}")
    print(f"[{time.strftime('%H:%M:%S')}] pipeline-watchdog")
    print(f"  主任务: {primary} | gate={'PASS' if gate.get('round2_unlocked') else 'BLOCK'}")
    print(f"  scheduler: running={sched.get('running')} scan_last={scan.get('last_run_iso','-')} rc={scan.get('last_rc','-')}")

    running = _running_summary(data_dir)
    print(f"  执行中 pipeline: {len(running)}")
    for r in running[:12]:
        mr = "Y" if r["has_result"] else "N"
        print(f"    {r['task_id'][:40]:40} {r['role']}/{r['assignee']} result={mr}")
    if len(running) > 12:
        print(f"    ... +{len(running)-12} more")

    rec = orch.get("reconcile") or {}
    if rec.get("cancelled_tasks") or rec.get("closed_inbox"):
        print(f"  编排修复: cancelled_tasks={rec.get('cancelled_tasks',0)} closed_inbox={rec.get('closed_inbox',0)}")

    anomalies = orch.get("anomalies") or []
    if anomalies:
        print(f"  异常 ({len(anomalies)}):")
        for a in anomalies[:8]:
            icon = SEVERITY_ICON.get(a.get("severity", "warn"), "⚠️")
            print(f"    {icon} [{a.get('code')}] {a.get('agent','')}: {a.get('detail')}")
    else:
        print("  异常: 无")

    healed = orch.get("healed") or {}
    if healed:
        print(f"  自愈: {healed}")
    print(f"{'='*60}\n")


def one_pass(data_dir: str, agents: dict, fix: bool) -> dict:
    orch = run_orchestrator(data_dir, agents, fix=fix, mode="light")
    if fix:
        healed = run_self_heal(data_dir, agents, phase="pre")
        orch["healed"] = healed
    return orch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=DATA)
    ap.add_argument("--no-fix", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="循环次数，0=只跑一轮")
    ap.add_argument("--interval", type=int, default=60, help="循环间隔秒")
    ap.add_argument("interval_pos", nargs="?", type=int, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.interval_pos is not None and args.loop:
        args.interval = args.interval_pos

    agents = json_read(os.path.join(args.data_dir, "config.json"), {}).get("agents", {})
    fix = not args.no_fix
    loops = max(1, args.loop) if args.loop else 1

    for i in range(loops):
        orch = one_pass(args.data_dir, agents, fix=fix)
        print_report(args.data_dir, agents, orch)
        if i < loops - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
