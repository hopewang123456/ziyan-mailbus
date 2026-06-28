#!/usr/bin/env python3
"""Dashboard API smoke — 配置中心 + 发布演练（等同浏览器点 Tab）。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.constants import DEFAULT_API_BASE
from lib.utils import configure_stdio_utf8

configure_stdio_utf8()


def get(path: str, base: str) -> tuple[int, dict]:
    req = urllib.request.Request(base.rstrip("/") + path)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def post(path: str, base: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main() -> int:
    from lib.env_bootstrap import load_mailbus_env

    load_mailbus_env()
    base = os.environ.get("MAILBUS_URL") or os.environ.get("MAILBUS_API") or DEFAULT_API_BASE
    ok = True

    print(f"== Dashboard API smoke @ {base} ==")

    for name, path in [
        ("status", "/api/status"),
        ("config", "/api/config"),
        ("agents", "/api/agents"),
        ("workflows", "/api/workflows"),
    ]:
        try:
            code, data = get(path, base)
            brief = "ok" if code == 200 else str(code)
            if path == "/api/config":
                brief += f" agents={len((data.get('agents') or {}))}"
            print(f"  PASS  GET {path} -> {brief}")
        except Exception as exc:
            ok = False
            print(f"  FAIL  GET {path} -> {exc}")

    try:
        code, data = post("/api/drill/video-publish", base, {"mode": "dry", "live": False})
        steps = data.get("steps") or []
        passed = sum(1 for s in steps if s.get("status") == "pass")
        drill_ok = data.get("ok", False)
        print(f"  {'PASS' if drill_ok else 'FAIL'}  POST /api/drill/video-publish dry -> {passed}/{len(steps)} steps")
        if not drill_ok:
            ok = False
            print(f"         error: {data.get('error')} {data.get('message', '')}")
    except Exception as exc:
        ok = False
        print(f"  FAIL  POST /api/drill/video-publish -> {exc}")

    try:
        if os.environ.get("N8N_PUBLISH_WEBHOOK_URL"):
            code, data = post("/api/drill/video-publish", base, {"mode": "live", "live": True})
            live_ok = data.get("ok", False)
            print(f"  {'PASS' if live_ok else 'WARN'}  POST /api/drill/video-publish live -> ok={live_ok}")
            if not live_ok:
                print(f"         {data.get('message') or data.get('error')}")
        else:
            print("  SKIP  live drill (N8N_PUBLISH_WEBHOOK_URL unset)")
    except Exception as exc:
        print(f"  WARN  live drill -> {exc}")

    print("== done ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
