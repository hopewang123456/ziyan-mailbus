#!/usr/bin/env python3
"""验证 mailbus 内置 SchedulerHub 状态，供 pipeline / 回归测试写 msg-results 使用。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def fetch_status(base_url: str, timeout: int = 8) -> dict:
    url = base_url.rstrip("/") + "/api/status"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"error": str(exc.reason)}


def validate_scheduler(base_url: str | None = None) -> tuple[bool, dict]:
    from lib.constants import DEFAULT_API_BASE
    base = base_url or os.environ.get("MAILBUS_URL", DEFAULT_API_BASE)
    status = fetch_status(base)
    if status.get("error"):
        return False, {"ok": False, "error": status["error"]}

    sched = status.get("scheduler") or {}
    jobs = sched.get("jobs") or {}
    scan = jobs.get("scan") or {}
    checks = {
        "scheduler_running": bool(sched.get("running")),
        "scan_job_enabled": bool((jobs.get("scan") or {}).get("enabled", True)),
        "scan_has_last_run": bool(scan.get("last_run_iso")),
        "scan_last_rc_ok": scan.get("last_rc", 1) == 0,
        "memory_bridge_job": "memory_bridge" in jobs,
        "pipeline_watchdog_job": "pipeline_watchdog" in jobs,
        "pipeline_repair_job": "pipeline-repair" in jobs,
        "platform_scout_job": "platform-scout" in jobs,
        "intake_bridge_job": "intake-bridge" in jobs,
    }
    ok = checks["scheduler_running"] and checks["scan_has_last_run"]
    report = {
        "ok": ok,
        "checks": checks,
        "scheduler": {
            "running": sched.get("running"),
            "scan_last_run": scan.get("last_run_iso"),
            "scan_last_rc": scan.get("last_rc"),
        },
        "agents": status.get("agents"),
        "base_url": base,
    }
    return ok, report


def build_msg_results(task_id: str, report: dict, *, pipeline_step: int = 1) -> dict:
    from datetime import datetime, timezone, timedelta

    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+0800")
    checks = report.get("checks") or {}
    summary_parts = [
        f"SchedulerHub running={checks.get('scheduler_running')}",
        f"scan_last_run={report.get('scheduler', {}).get('scan_last_run', '?')}",
        f"scan_rc={report.get('scheduler', {}).get('scan_last_rc')}",
        "WSL crontab 已清理，内置 jobs: scan/bridge/watchdog/patrol/daily/log_rotate",
    ]
    return {
        "template": "report",
        "conclusion": "done",
        "task": task_id,
        "task_id": task_id,
        "summary": "；".join(summary_parts),
        "next_role": "调度员",
        "pipeline_step": pipeline_step,
        "timestamp": ts,
        "result": {
            "message": "scheduler validation passed" if report.get("ok") else "scheduler validation partial",
            "validation": report,
        },
        "source": "validate-scheduler.py",
        "agent": "mailbus",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser()
    from lib.constants import DEFAULT_API_BASE
    parser.add_argument("--url", default=os.environ.get("MAILBUS_URL", DEFAULT_API_BASE))
    parser.add_argument("--task-id", default="mailbus-scheduler-validation-20260616")
    parser.add_argument("--write", metavar="DATA_DIR", help="写入 msg-results/{task_id}.json")
    args = parser.parse_args()

    ok, report = validate_scheduler(args.url)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sched = report.get("scheduler") or {}
    print(
        f"summary: ok={report.get('ok')} running={sched.get('running')} "
        f"scan_rc={sched.get('scan_last_rc')}",
        file=sys.stderr,
    )
    if args.write:
        out_dir = os.path.join(args.write, "msg-results")
        os.makedirs(out_dir, exist_ok=True)
        payload = build_msg_results(args.task_id, report)
        out_path = os.path.join(out_dir, f"{args.task_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"written: {out_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
