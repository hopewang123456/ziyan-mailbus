#!/usr/bin/env python3
"""持续监控 Round1 pipeline，输出单行摘要。用法: watch-round1.py [--loop N]"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utils import json_read, resolve_paths
from lib.scanner import get_msg_state, build_queues, recover_inbox_stale_states
from lib.tracker import TaskTracker
from lib.iteration_engine import evaluate_round1_gate

DATA = os.environ.get("MAILBUS_DATA", "store")
TASK = "mailbus-hardening-20260616"


def hermes_chat_count(profile: str = "") -> int:
    try:
        r = subprocess.run(
            ["docker", "exec", "docker-agents-hermes-1", "ps", "aux"],
            capture_output=True, text=True, timeout=10,
        )
        lines = [l for l in r.stdout.splitlines() if "hermes chat" in l and "grep" not in l]
        if profile:
            lines = [l for l in lines if f"--profile {profile}" in l]
        return len(lines)
    except Exception:
        return -1


def snapshot(agents: dict) -> str:
    t = TaskTracker(DATA).get(TASK) or {}
    result = os.path.join(DATA, "msg-results", f"{TASK}.json")
    gate = evaluate_round1_gate(DATA, agents)

    hardening_states = []
    inbox_file = f"{resolve_paths(DATA)['inbox']}/lingzhao/inbox.json"
    for m in json_read(inbox_file, {}).get("messages", []):
        if TASK in m.get("content", ""):
            hardening_states.append(f"{m['id'][-5:]}:{get_msg_state(m)}")

    uq, nq = build_queues(DATA, agents)
    lz_head = "-"
    if "lingzhao" in uq:
        lz_head = uq["lingzhao"][0].id[-12:]
    elif "lingzhao" in nq:
        lz_head = nq["lingzhao"][0].id[-12:]

    chats = hermes_chat_count("lingzhao")
    chats_bad = hermes_chat_count() - hermes_chat_count("lingzhao") if chats >= 0 else -1

    return (
        f"task={t.get('status','?')} "
        f"result={'Y' if os.path.exists(result) else 'N'} "
        f"gate={'OK' if gate.get('round2_unlocked') else 'BLOCK'} "
        f"lz_q={lz_head} "
        f"msgs=[{','.join(hardening_states[:3])}] "
        f"hermes_lz={chats} hermes_noprofile={max(0, chats_bad)}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="循环秒数，0=只跑一轮")
    ap.add_argument("--scan", action="store_true", help="每轮后执行 bus scan")
    args = ap.parse_args()

    agents = json_read(os.path.join(DATA, "config.json"), {}).get("agents", {})

    while True:
        line = f"[{time.strftime('%H:%M:%S')}] {snapshot(agents)}"
        print(line, flush=True)
        if args.scan:
            subprocess.run(
                [sys.executable, "bus.py", "scan"],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                timeout=300,
            )
        if args.loop <= 0:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
