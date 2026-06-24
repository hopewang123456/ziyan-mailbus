#!/usr/bin/env python3
"""v3 全链自动化验收 — 12 步 LIVE，禁止 advance 代写。

轮询 msg-results / chain / inbox，每步超时告警，终态 success 或失败报告。

用法:
  python3 tools/run-v3-autovalidation.py --task-id game-stellar-20260618
  python3 tools/run-v3-autovalidation.py --task-id game-stellar-20260618 --submit
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

TZ_CN = timezone(timedelta(hours=8))
MAIL_ROOT = os.environ.get("MAILBUS_ROOT", "/mailbus")
STEPS = 12
AGENTS_PLANNED = [
    "lingzhao", "lingxi", "lingzhao", "xiaoqi", "lingxiao", "dali",
    "lingjin", "lingjian", "lingyan", "lingxun", "lingtuo", "lingzhang", "yige", "xiaoqi",
]


def log(msg: str) -> None:
    ts = datetime.now(TZ_CN).strftime("%H:%M:%S")
    print(f"[v3-auto {ts}] {msg}", flush=True)


def load_task(data_dir: str, task_id: str) -> dict:
    p = os.path.join(data_dir, "tasks", f"{task_id}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}


def current_step(task: dict) -> tuple[int, str, str]:
    chain = task.get("chain") or []
    if not chain:
        return 0, "", ""
    cur = chain[-1]
    return int(cur.get("step") or len(chain)), cur.get("to_person", ""), cur.get("status", "")


def scan(data_dir: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "bus", "scan", "--data-dir", data_dir],
        cwd=MAIL_ROOT,
        timeout=180,
        check=False,
    )


def submit_v3(task_id: str) -> None:
    script = os.path.join(MAIL_ROOT, "docker-agents", "submit-game-stellar-v3-live-docker.sh")
    subprocess.run(["bash", script, task_id], check=True, timeout=300)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", default="game-stellar-20260618")
    ap.add_argument("--data-dir", default="store")
    ap.add_argument("--submit", action="store_true", help="先执行 submit 脚本")
    ap.add_argument("--step-timeout", type=int, default=3600, help="每步最大等待秒")
    ap.add_argument("--poll", type=int, default=30)
    args = ap.parse_args()
    data_dir = os.path.abspath(args.data_dir)

    if args.submit:
        log("submit v3 task...")
        submit_v3(args.task_id)

    last_step = 0
    step_started = time.time()
    deadline_global = time.time() + args.step_timeout * STEPS

    while time.time() < deadline_global:
        task = load_task(data_dir, args.task_id)
        if not task:
            log(f"FAIL task file missing: {args.task_id}")
            return 1

        status = task.get("status", "")
        step, agent, step_st = current_step(task)
        chain_len = len(task.get("chain") or [])

        mr_path = os.path.join(data_dir, "msg-results", f"{args.task_id}.json")
        mr = json.load(open(mr_path, encoding="utf-8")) if os.path.isfile(mr_path) else None
        mr_info = ""
        if mr:
            mr_info = f" mr: step={mr.get('pipeline_step')} agent={mr.get('agent')}"

        log(f"status={status} chain_steps={chain_len} cur=Step{step}/{agent}({step_st}){mr_info}")

        if status == "success":
            log(f"PASS v3 complete {args.task_id}")
            return 0
        if status in ("failed", "cancelled", "timeout"):
            log(f"FAIL task terminal status={status}")
            return 1

        if step > last_step:
            last_step = step
            step_started = time.time()
            log(f"→ advanced to Step{step} ({agent})")

        if time.time() - step_started > args.step_timeout:
            log(f"FAIL Step{step} timeout ({args.step_timeout}s) agent={agent}")
            return 1

        scan(data_dir)
        time.sleep(args.poll)

    log("FAIL global timeout")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
