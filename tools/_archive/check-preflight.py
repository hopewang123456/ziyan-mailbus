#!/usr/bin/env python3
"""mailbus live 验收 pre-flight：容器/API/agent/iteration 状态检查。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.constants import DEFAULT_DATA_DIR
from lib.tracker import TaskStatus, TaskTracker
from lib.utils import json_read, resolve_paths

PIPELINE_AGENTS = (
    "lingzhao", "lingxi", "xiaoqi", "lingxiao", "dali",
    "lingjin", "lingjian", "lingyan", "lingxun", "yige",
)


def _get(url: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _docker_ps() -> set[str]:
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if out.returncode != 0:
            return set()
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()


def check_api(base: str) -> tuple[bool, str]:
    try:
        data = _get(f"{base.rstrip('/')}/api/status")
        return "agents" in data or "project" in data, json.dumps(
            {"agents": data.get("agents"), "unread": data.get("unread_messages")},
            ensure_ascii=False,
        )[:200]
    except Exception as exc:
        return False, str(exc)


def check_scheduler(base: str) -> tuple[bool, str]:
    try:
        data = _get(f"{base.rstrip('/')}/api/system/scheduler")
        jobs = data.get("jobs") or []
        scan = next((j for j in jobs if j.get("id") == "scan"), None)
        if not scan:
            return False, "scan job missing"
        return True, f"jobs={len(jobs)} scan_enabled={scan.get('enabled')}"
    except Exception as exc:
        return False, str(exc)


def check_iteration(data_dir: str, *, allow_primary: str = "") -> tuple[bool, str]:
    state = json_read(os.path.join(data_dir, "iterations", "iteration-state.json"), {})
    primary = state.get("primary_task_id") or ""
    if not primary:
        return True, "no primary_task_id"
    tr = TaskTracker(data_dir)
    t = tr.get(primary) or {}
    st = t.get("status", "")
    if allow_primary and primary == allow_primary and st in (TaskStatus.RUNNING, TaskStatus.PENDING):
        return True, f"primary={primary} status={st} (live acceptance)"
    if st in (TaskStatus.RUNNING, TaskStatus.PENDING) and primary != allow_primary:
        return False, f"blocking primary {primary} status={st}"
    return True, f"primary={primary} status={st}"


def check_agents(data_dir: str, names: tuple[str, ...]) -> tuple[bool, list[str]]:
    paths = resolve_paths(data_dir)
    issues = []
    for name in names:
        inbox = os.path.join(paths["inbox"], name, "inbox.json")
        if not os.path.isfile(inbox):
            issues.append(f"{name}: no inbox")
    return len(issues) == 0, issues


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", DEFAULT_DATA_DIR))
    p.add_argument("--api", default=os.environ.get("MAILBUS_API", "http://127.0.0.1:9814"))
    p.add_argument("--task-id", default="", help="可选：检查指定 pipeline 任务")
    args = p.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    blockers: list[str] = []

    ok, detail = check_api(args.api)
    print(f"api: {'OK' if ok else 'FAIL'} — {detail}")
    if not ok:
        blockers.append("api")

    ok, detail = check_scheduler(args.api)
    print(f"scheduler: {'OK' if ok else 'WARN'} — {detail}")

    ok, detail = check_iteration(data_dir, allow_primary=args.task_id)
    print(f"iteration: {'OK' if ok else 'BLOCK'} — {detail}")
    if not ok:
        blockers.append("iteration")

    containers = _docker_ps()
    if containers:
        mailbus_up = any("mailbus" in c for c in containers)
        print(f"docker: {len(containers)} containers mailbus={'up' if mailbus_up else 'missing'}")
        if not mailbus_up:
            blockers.append("docker-mailbus")
    else:
        print("docker: unavailable (skip)")

    ok, issues = check_agents(data_dir, PIPELINE_AGENTS)
    print(f"agents: {'OK' if ok else 'FAIL'} — {len(PIPELINE_AGENTS)} checked")
    for issue in issues:
        print(f"  - {issue}")
        blockers.append(issue)

    if args.task_id:
        tr = TaskTracker(data_dir)
        t = tr.get(args.task_id)
        if not t:
            print(f"task {args.task_id}: NOT_FOUND")
            blockers.append("task-missing")
        else:
            chain = t.get("chain") or []
            step = chain[-1] if chain else {}
            print(
                f"task {args.task_id}: status={t.get('status')} "
                f"step={step.get('step')} assignee={step.get('to_person') or t.get('assignee')}"
            )

    if blockers:
        print(f"PREFLIGHT: BLOCKED ({len(blockers)} issues)")
        return 1
    print("PREFLIGHT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
