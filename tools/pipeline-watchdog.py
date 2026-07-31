#!/usr/bin/env python3
"""CLI: pipeline watchdog — delegates to application.ops.pipeline_watchdog."""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.ops.pipeline_watchdog import collect_watchdog_context, run_watchdog_pass
from lib.utils import json_read

DATA = os.environ.get("MAILBUS_DATA", "store")
SEVERITY_ICON = {"critical": "🔴", "warn": "⚠️", "info": "ℹ️"}


def print_report(data_dir: str, agents: dict, orch: dict) -> None:
    ctx = collect_watchdog_context(data_dir, agents)
    gate = ctx.get("gate") or {}
    sched = ctx.get("scheduler") or {}
    scan = ctx.get("scan") or {}
    running = ctx.get("running") or []

    print(f"\n{'='*60}")
    print(f"[{time.strftime('%H:%M:%S')}] pipeline-watchdog")
    print(f"  主任务: {ctx.get('primary_task_id', '?')} | gate={'PASS' if gate.get('round2_unlocked') else 'BLOCK'}")
    print(f"  scheduler: running={sched.get('running')} scan_last={scan.get('last_run_iso','-')} rc={scan.get('last_rc','-')}")

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


def main() -> None:
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
        orch = run_watchdog_pass(args.data_dir, agents, fix=fix)
        print_report(args.data_dir, agents, orch)
        if i < loops - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
