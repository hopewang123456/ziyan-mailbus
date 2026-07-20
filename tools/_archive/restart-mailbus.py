#!/usr/bin/env python3
"""Restart native mailbus serve (cross-platform, Windows-friendly)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pids_on_port(port: int) -> list[int]:
    if sys.platform == "win32":
        out = subprocess.check_output(
            ["netstat", "-ano"], text=True, errors="replace", timeout=30,
        )
        pids: set[int] = set()
        token = f":{port}"
        for line in out.splitlines():
            if "LISTENING" not in line.upper() or token not in line:
                continue
            parts = line.split()
            if parts:
                try:
                    pids.add(int(parts[-1]))
                except ValueError:
                    pass
        return sorted(pids)
    out = subprocess.check_output(["ss", "-ltnp"], text=True, errors="replace", timeout=30)
    # fallback: lsof
    pids: set[int] = set()
    try:
        out2 = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True, timeout=15)
        for line in out2.splitlines():
            try:
                pids.add(int(line.strip()))
            except ValueError:
                pass
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return sorted(pids)


def _stop_port(port: int) -> None:
    for pid in _pids_on_port(port):
        if pid <= 0:
            continue
        print(f"[restart] stop pid {pid} on port {port}")
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        else:
            os.kill(pid, 15)


def _health(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _reports_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/reports", timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Restart mailbus serve")
    ap.add_argument("--port", type=int, default=9814)
    args = ap.parse_args()
    port = args.port
    log_dir = os.path.join(ROOT, "store", "logs")
    os.makedirs(log_dir, exist_ok=True)
    out_log = os.path.join(log_dir, "mailbus-serve.out.log")
    err_log = os.path.join(log_dir, "mailbus-serve.err.log")

    _stop_port(port)
    time.sleep(2)

    with open(out_log, "a", encoding="utf-8") as out, open(err_log, "a", encoding="utf-8") as err:
        subprocess.Popen(
            [
                sys.executable,
                os.path.join(ROOT, "bus.py"),
                "serve",
                "--host", "127.0.0.1",
                "--port", str(port),
                "--data-dir", os.path.join(ROOT, "store"),
            ],
            cwd=ROOT,
            stdout=out,
            stderr=err,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    for _ in range(20):
        time.sleep(2)
        if _health(port) and _reports_ok(port):
            print(f"[restart] OK http://127.0.0.1:{port}/")
            return 0
    print(f"[restart] mailbus not ready on {port}; see {out_log} and {err_log}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
