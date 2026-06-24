#!/usr/bin/env python3
"""Poll Round1 until msg-results or timeout."""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.utils import json_read
from lib.iteration_engine import load_primary_task_id

DATA = os.environ.get("MAILBUS_DATA", "store")
TASK = load_primary_task_id(os.path.abspath(DATA))
RESULT = f"{DATA}/msg-results/{TASK}.json"
agents = json_read(f"{DATA}/config.json", {}).get("agents", {})


def hermes_running() -> bool:
    try:
        r = subprocess.run(
            ["docker", "exec", "docker-agents-hermes-1", "ps", "aux"],
            capture_output=True, text=True, timeout=10,
        )
        return "profile lingzhao" in r.stdout and "hermes chat" in r.stdout
    except Exception:
        return False


def main():
    for i in range(12):
        exists = os.path.exists(RESULT)
        running = hermes_running()
        print(f"[{time.strftime('%H:%M:%S')}] poll={i+1} result={'Y' if exists else 'N'} hermes={'run' if running else 'idle'}")
        if exists:
            print("SUCCESS:", RESULT)
            subprocess.run([sys.executable, "bus.py", "scan"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            subprocess.run([sys.executable, "tools/round1-status.py"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return 0
        if not running and i > 0:
            subprocess.run([sys.executable, "bus.py", "scan"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        time.sleep(30)
    print("TIMEOUT waiting for msg-results")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
