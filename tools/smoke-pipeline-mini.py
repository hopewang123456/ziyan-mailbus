#!/usr/bin/env python3
"""Mini pipeline 自动化 — 2 步验证：落盘 + pipeline_trigger 推进。

Step1 lingzhao → Step2 lingxi。每步等待 msg-results，scan 触发推进。
用于 v3 全链跑前的 gate。

用法:
  python3 tools/smoke-pipeline-mini.py
  python3 tools/smoke-pipeline-mini.py --step-timeout 600
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

TZ_CN = timezone(timedelta(hours=8))
MAIL_ROOT = os.environ.get("MAILBUS_ROOT", "/mailbus")
API = os.environ.get("MAILBUS_API", "http://127.0.0.1:9814")
CHAIN = ["lingzhao", "lingxi"]


def log(msg: str) -> None:
    print(f"[smoke-mini] {msg}", flush=True)


def api_post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def scan(data_dir: str) -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "bus", "scan", "--data-dir", data_dir],
            cwd=MAIL_ROOT,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log("  scan timeout (300s), continue polling")


def read_result(data_dir: str, task_id: str) -> dict | None:
    p = os.path.join(data_dir, "msg-results", f"{task_id}.json")
    if not os.path.isfile(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def wait_step(data_dir: str, task_id: str, agent: str, step: int, timeout: int, poll: int) -> bool:
    deadline = time.time() + timeout
    n = 0
    while time.time() < deadline:
        n += 1
        r = read_result(data_dir, task_id)
        if r and r.get("agent") == agent and int(r.get("pipeline_step", 0)) == step:
            log(f"  Step{step} PASS agent={agent} summary={str(r.get('summary',''))[:60]}")
            return True
        log(f"  Step{step} wait round={n} (no valid msg-results yet)")
        time.sleep(poll)
        if n % 2 == 0:
            scan(data_dir)
    return False


def set_primary_task(data_dir: str, task_id: str) -> dict:
    """临时设 primary_task_id，返回原 state 供恢复。"""
    state_path = os.path.join(data_dir, "iterations", "iteration-state.json")
    prev = {}
    if os.path.isfile(state_path):
        prev = json.load(open(state_path, encoding="utf-8"))
    nxt = dict(prev)
    nxt["primary_task_id"] = task_id
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(nxt, f, ensure_ascii=False, indent=2)
    log(f"primary_task_id -> {task_id}")
    return prev


def restore_primary_task(data_dir: str, prev: dict) -> None:
    if not prev:
        return
    state_path = os.path.join(data_dir, "iterations", "iteration-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(prev, f, ensure_ascii=False, indent=2)
    log(f"primary_task_id restored -> {prev.get('primary_task_id', '')}")


def push_step1(data_dir: str, task_id: str) -> None:
    subprocess.run(
        [
            sys.executable, os.path.join(MAIL_ROOT, "tools", "pipeline-push-step1.py"),
            "--data-dir", data_dir,
            "--task-id", task_id,
            "--agent", "lingzhao",
        ],
        cwd=MAIL_ROOT,
        check=True,
        timeout=120,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="store")
    ap.add_argument("--step-timeout", type=int, default=600)
    ap.add_argument("--poll", type=int, default=20)
    args = ap.parse_args()
    data_dir = os.path.abspath(args.data_dir)

    task_id = f"pipeline-mini-{datetime.now(TZ_CN).strftime('%Y%m%d-%H%M%S')}"
    log(f"task_id={task_id} chain={' → '.join(CHAIN)}")

    prev_primary = {}
    exit_code = 1
    try:
        prev_primary = set_primary_task(data_dir, task_id)

        # cleanup old result
        mr = os.path.join(data_dir, "msg-results", f"{task_id}.json")
        if os.path.isfile(mr):
            os.remove(mr)

        log("1. create 2-step task (Envelope)")
        api_post("/api/tasks/create", {
            "protocol_version": "mailbus-a2a/1",
            "task_id": task_id,
            "intent": f"Mini pipeline probe {task_id}",
            "initiator": "human",
            "mode": "explicit",
            "tier": "S",
            "task_type": "spike",
            "planned_chain": [
                {"role_type": 1},
                {"role_type": 3},
            ],
        })

        log("2. push Step1 (lingzhao)")
        push_step1(data_dir, task_id)
        scan(data_dir)

        log("3. wait Step1 msg-results")
        if not wait_step(data_dir, task_id, "lingzhao", 1, args.step_timeout, args.poll):
            log("FAIL Step1")
            return 1

        log("4. scan → trigger Step2")
        scan(data_dir)
        time.sleep(5)
        scan(data_dir)

        # Step2 overwrites same msg-results file with pipeline_step=2
        log("5. wait Step2 msg-results (lingxi)")
        if not wait_step(data_dir, task_id, "lingxi", 2, args.step_timeout, args.poll):
            log("FAIL Step2")
            return 1

        log(f"PASS mini pipeline {task_id}")
        exit_code = 0
    finally:
        restore_primary_task(data_dir, prev_primary)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
