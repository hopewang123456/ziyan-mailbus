#!/usr/bin/env python3
"""Phase 5 live E2E — real dali/opencode CLI via Docker push + Normalizer gate.

Creates a single-step pipeline (role_type=8 / dali), pushes via mailbus scan,
waits for step msg-results (not phantom patch-only), verifies FSM can read result.

用法:
  python tools/live-dali-opencode-e2e.py --data-dir store
  MAILBUS_ROOT=/mnt/e/ai_tools/mail python tools/live-dali-opencode-e2e.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

TZ_CN = timezone(timedelta(hours=8))
MAIL_ROOT = os.environ.get("MAILBUS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API = os.environ.get("MAILBUS_API", "http://127.0.0.1:9814")

sys.path.insert(0, MAIL_ROOT)

from lib.delivery_normalizer import normalize_opencode_deliveries
from lib.file_task_push import verify_file_task_delivery
from lib.phantom_detect import is_phantom_reply_text
from lib.task_fsm import read_step_result
from lib.utils import json_read


def log(msg: str) -> None:
    print(f"[live-dali-e2e] {msg}", flush=True)


def api_post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def scan(data_dir: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "bus", "scan", "--data-dir", data_dir],
        cwd=MAIL_ROOT,
        timeout=600,
        check=False,
    )


def push_step1(data_dir: str, task_id: str) -> None:
    subprocess.run(
        [
            sys.executable,
            os.path.join(MAIL_ROOT, "tools", "pipeline-push-step1.py"),
            "--data-dir",
            data_dir,
            "--task-id",
            task_id,
            "--agent",
            "dali",
        ],
        cwd=MAIL_ROOT,
        check=True,
        timeout=120,
    )


def step_result_path(data_dir: str, task_id: str, step_id: str) -> str:
    return os.path.join(data_dir, "msg-results", task_id, f"step-{step_id}.json")


def wait_step_result(
    data_dir: str,
    task_id: str,
    step_id: str,
    *,
    timeout: int,
    poll: int,
) -> dict | None:
    deadline = time.time() + timeout
    n = 0
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = cfg.get("agents") or {}
    while time.time() < deadline:
        n += 1
        normalize_opencode_deliveries(data_dir, agents)
        path = step_result_path(data_dir, task_id, step_id)
        if os.path.isfile(path):
            result = json_read(path, {})
            status = (result.get("status") or result.get("conclusion") or "").lower()
            if status in ("done", "pass", "submitted", "ok"):
                log(f"step result OK path={path} summary={str(result.get('summary', ''))[:80]}")
                return result
        log(f"wait round={n} (no step result yet)")
        time.sleep(poll)
        if n % 2 == 0:
            scan(data_dir)
    return None


def docker_ps_names() -> str:
    if shutil.which("docker"):
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.stdout or ""
    wsl = shutil.which("wsl")
    if wsl:
        proc = subprocess.run(
            [wsl, "docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.stdout or ""
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="store")
    ap.add_argument("--step-timeout", type=int, default=900)
    ap.add_argument("--poll", type=int, default=30)
    args = ap.parse_args()
    data_dir = os.path.abspath(os.path.join(MAIL_ROOT, args.data_dir))

    task_id = f"p5-dali-live-{datetime.now(TZ_CN).strftime('%Y%m%d-%H%M%S')}"
    step_id = "s1"
    log(f"task_id={task_id} agent=dali framework=opencode")

    # preflight: dali container + API
    try:
        urllib.request.urlopen(f"{API.rstrip('/')}/api/status", timeout=10)
    except OSError as exc:
        log(f"FAIL API unreachable: {exc}")
        return 1
    if "docker-agents-dali-1" not in docker_ps_names():
        log("FAIL docker-agents-dali-1 not running")
        return 1

    log("1. create single-step Envelope (role_type=8 → dali)")
    api_post("/api/tasks/create", {
        "protocol_version": "mailbus-a2a/1",
        "task_id": task_id,
        "intent": f"P5 live dali/opencode smoke {task_id}: write deliverables/{task_id}/P5_LIVE_OK.txt",
        "initiator": "human",
        "mode": "explicit",
        "tier": "S",
        "task_type": "spike",
        "planned_chain": [{"role_type": 8}],
    })

    log("2. push Step1 to dali (real opencode via scan)")
    push_step1(data_dir, task_id)
    scan(data_dir)

    log("3. wait msg-results step gate (Normalizer + no phantom)")
    result = wait_step_result(
        data_dir, task_id, step_id, timeout=args.step_timeout, poll=args.poll,
    )
    if not result:
        log("FAIL: timeout waiting for step msg-results")
        return 1

    task = json_read(os.path.join(data_dir, "tasks", f"{task_id}.json"), {})
    chain = task.get("chain") or []
    step = chain[0] if chain else {}
    fsm_read = read_step_result(data_dir, task_id, step)
    if not fsm_read:
        log("FAIL: FSM cannot read step result")
        return 1

    inbox = json_read(os.path.join(data_dir, "inbox", "dali", "inbox.json"), {})
    for m in (inbox.get("messages") or []):
        if m.get("task_id") != task_id:
            continue
        ok, reason = verify_file_task_delivery(
            data_dir, "dali", m, reply_text=m.get("reply_text") or "",
        )
        if not ok and reason == "phantom_reply_text":
            log("FAIL: phantom reply would pass without msg-results")
            return 1

    if is_phantom_reply_text("已完成", msg_type="task"):
        log("phantom detector active (sanity)")

    log(f"PASS live dali/opencode E2E {task_id}")
    report = {
        "task_id": task_id,
        "step_id": step_id,
        "agent": "dali",
        "framework": "opencode",
        "result_path": step_result_path(data_dir, task_id, step_id),
        "summary": result.get("summary", ""),
        "verified_at": datetime.now(TZ_CN).isoformat(),
    }
    out = os.path.join(data_dir, "msg-results", f"{task_id}-live-e2e.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
