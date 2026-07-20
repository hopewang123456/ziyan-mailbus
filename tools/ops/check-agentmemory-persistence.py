#!/usr/bin/env python3
"""AgentMemory 持久化探针 — 写入 → 重启 iii-engine → 验证记忆仍在。

用法:
  python3 tools/ops/check-agentmemory-persistence.py
  python3 tools/ops/check-agentmemory-persistence.py --dry-run
  python3 tools/ops/check-agentmemory-persistence.py --url http://127.0.0.1:3111
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get(
    "AGENTMEMORY_URL",
    "http://iii-engine:3111" if os.path.exists("/.dockerenv") else "http://127.0.0.1:3111",
)


def _get_json(url: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _memory_count(export: dict) -> int:
    if isinstance(export.get("memories"), list):
        return len(export["memories"])
    if isinstance(export.get("count"), int):
        return export["count"]
    stats = export.get("stats") or {}
    if isinstance(stats.get("memories"), int):
        return stats["memories"]
    return 0


def _compose_file() -> str:
    compose_dir = os.environ.get(
        "MAILBUS_COMPOSE_DIR",
        "/mailbus/docker-agents" if os.path.isdir("/mailbus/docker-agents") else "",
    )
    if not compose_dir:
        compose_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "docker-agents",
        )
    return os.path.join(compose_dir, "docker-compose.yml")


def _restart_iii_engine(dry_run: bool) -> bool:
    compose_file = _compose_file()
    if dry_run:
        print(f"[dry-run] would restart iii-engine via {compose_file}")
        return True
    if not os.path.isfile(compose_file):
        print(f"ERROR: compose file not found: {compose_file}", file=sys.stderr)
        return False
    if not os.path.exists("/var/run/docker.sock"):
        print("ERROR: docker.sock unavailable", file=sys.stderr)
        return False
    r = subprocess.run(
        ["docker", "compose", "-f", compose_file, "restart", "iii-engine"],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        print(f"ERROR: restart failed: {(r.stderr or r.stdout)[:300]}", file=sys.stderr)
        return False
    return True


def _wait_health(base: str, seconds: int = 60) -> bool:
    for i in range(seconds):
        try:
            data = _get_json(f"{base.rstrip('/')}/agentmemory/health", timeout=5)
            if data.get("status") == "healthy":
                print(f"  health ok after {i + 1}s")
                return True
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentMemory persistence probe")
    parser.add_argument("--url", default=DEFAULT_URL, help="AgentMemory base URL")
    parser.add_argument("--dry-run", action="store_true", help="Skip docker restart")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    try:
        export_before = _get_json(f"{base}/agentmemory/export")
    except Exception as exc:
        print(f"FAIL: cannot export before probe: {exc}")
        return 1

    count_before = _memory_count(export_before)
    probe_id = f"mailbus-persist-probe-{int(time.time())}"
    payload = {
        "content": f"[mailbus-persist-probe] {probe_id}",
        "metadata": {"source": "check-agentmemory-persistence", "probe_id": probe_id},
    }

    try:
        result = _post_json(f"{base}/agentmemory/remember", payload)
    except Exception as exc:
        print(f"FAIL: remember failed: {exc}")
        return 1

    if not (result.get("success") or result.get("memory")):
        print(f"FAIL: remember rejected: {result}")
        return 1

    print(f"OK: probe written ({probe_id})")

    if not _restart_iii_engine(args.dry_run):
        return 1

    if not args.dry_run:
        if not _wait_health(base):
            print("FAIL: health not recovered after restart")
            return 1
        try:
            export_after = _get_json(f"{base}/agentmemory/export")
        except Exception as exc:
            print(f"FAIL: cannot export after restart: {exc}")
            return 1
        count_after = _memory_count(export_after)
        if count_after < count_before + 1:
            print(f"FAIL: memory count dropped ({count_before} -> {count_after})")
            return 1
        print(f"OK: persistence verified ({count_before} -> {count_after})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
