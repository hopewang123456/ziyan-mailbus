#!/usr/bin/env python3
"""容器内轮询 mini pipeline Step2。"""
import glob
import json
import os
import subprocess
import sys
import time

DATA = os.environ.get("DATA_DIR", "/mailbus/store")


def _latest_mini_task() -> str:
    tasks = sorted(glob.glob(os.path.join(DATA, "tasks", "pipeline-mini-*.json")), reverse=True)
    if not tasks:
        return ""
    return os.path.basename(tasks[0]).replace(".json", "")


TASK = os.environ.get("TASK_ID") or _latest_mini_task()
MR = f"{DATA}/msg-results/{TASK}.json"


def read_mr():
    if not os.path.isfile(MR):
        return {}
    return json.load(open(MR, encoding="utf-8"))


def main():
    if not TASK:
        print("ERROR: no pipeline-mini task found")
        return 1
    print(f"poll task_id={TASK}", flush=True)
    timeout = int(os.environ.get("TIMEOUT", "600"))
    poll = int(os.environ.get("POLL", "30"))
    deadline = time.time() + timeout
    n = 0
    while time.time() < deadline:
        n += 1
        mr = read_mr()
        print(f"[poll {n}] agent={mr.get('agent')} step={mr.get('pipeline_step')}", flush=True)
        if mr.get("agent") == "lingxi" and int(mr.get("pipeline_step", 0)) == 2:
            print("STEP2 PASS")
            return 0
        subprocess.run(
            [sys.executable, "-m", "bus", "scan", "--data-dir", DATA],
            cwd="/mailbus",
            timeout=300,
            check=False,
        )
        time.sleep(poll)
    print("STEP2 TIMEOUT")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
