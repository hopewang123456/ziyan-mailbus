#!/usr/bin/env python3
"""Probe mailbus HTTP API endpoints (GET + sample POST)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("MAILBUS_URL", "http://127.0.0.1:9814").rstrip("/")

GET_PATHS = [
    "/",
    "/api/status",
    "/api/agents",
    "/api/frameworks",
    "/api/tasks",
    "/api/heartbeat",
    "/api/alerts",
    "/api/config",
    "/api/stats",
    "/api/launch",
    "/api/bulletin",
    "/api/bulletin/permit",
    "/api/permission",
    "/api/reports",
    "/api/patrol-reports",
    "/api/reviews",
    "/api/reviews/projects",
    "/api/replies",
    "/api/skill-usage",
    "/api/templates",
    "/api/external-tools",
    "/api/clinic/tools",
    "/api/doctor",
    "/api/workload",
    "/api/internal-llm/status",
    "/api/internal-llm/health",
    "/api/workflows",
    "/api/intake",
    "/api/settings/sections",
    "/api/settings/env",
    "/api/a2a/agent-cards",
    "/api/a2a/protocol",
    "/api/human-queue",
    "/api/search?q=test",
]

POST_CHECKS = [
    ("/api/launch", {"agent": "lingyun", "mode": "browser"}),
    ("/api/launch", {"agent": "lingxiao", "mode": "browser"}),
]

CLI_POST_CHECKS = [
    "lingxi",
    "lingzhao",
    "lingxiao",
    "lingyun",
    "lingyan",
    "xiaoqi",
    "dali",
]


def probe(method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            chunk = resp.read(300)
            return resp.status, chunk.decode("utf-8", errors="replace")[:120]
    except urllib.error.HTTPError as e:
        chunk = e.read(300)
        return e.code, chunk.decode("utf-8", errors="replace")[:120]
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"[:120]


def main() -> int:
    fails = 0
    print(f"BASE={BASE}\n")
    print("=== GET ===")
    for path in GET_PATHS:
        code, snippet = probe("GET", path)
        ok = 200 <= code < 400
        mark = "OK" if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"{mark:4} {code:3} GET {path}")
        if not ok:
            print(f"      {snippet}")

    print("\n=== POST (launch browser) ===")
    for path, body in POST_CHECKS:
        code, snippet = probe("POST", path, body)
        ok = 200 <= code < 400
        mark = "OK" if ok else "FAIL"
        if not ok:
            fails += 1
        agent = body.get("agent", "?")
        print(f"{mark:4} {code:3} POST {path} agent={agent} mode=browser")
        if not ok or "error" in snippet.lower():
            print(f"      {snippet}")

    print("\n=== POST (launch cli) ===")
    for agent in CLI_POST_CHECKS:
        code, snippet = probe("POST", "/api/launch", {"agent": agent, "mode": "cli"})
        ok = 200 <= code < 400
        mark = "OK" if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"{mark:4} {code:3} POST /api/launch agent={agent} mode=cli")
        if not ok or "error" in snippet.lower():
            print(f"      {snippet}")

    print(f"\nDone: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
