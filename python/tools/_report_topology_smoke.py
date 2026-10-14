#!/usr/bin/env python3
"""Summarize agent card topology + probe browser/CLI for user report."""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from shutil import which

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "store" / "config.json"
DATA = ROOT / "store"

PORT_HINTS = {
    "lingzhao": 9120,
    "lingjin": 9121,
    "lingtuo": 9122,
    "lingxi": 9123,
    "lingxun": 9125,
    "lingzhang": 9126,
    "xiaoqi": 18789,
    "yige": 18790,
    "lingxiao": 9250,
    "lingjian": 9251,
    "lingyan": 9260,
    "lingyun": 9261,
}


def http_code(url: str, timeout: float = 4.0):
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"ERR:{type(e).__name__}"


def wsl(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["wsl", "-d", "Ubuntu", "-e", "bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (r.stdout or r.stderr or "").strip()
    except Exception as e:
        return f"ERR:{e}"


def main() -> None:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    agents = cfg.get("agents") or {}
    print("=== agent cards (run_target / host:port / type) ===")
    by_type: dict[str, list] = {}
    for aid, rec in sorted(agents.items()):
        if not isinstance(rec, dict):
            continue
        at = (rec.get("type") or "?").strip()
        by_type.setdefault(at, []).append(aid)
        print(
            f"  {aid:12} type={at:14} rt={rec.get('run_target','?'):8} "
            f"{rec.get('host','?')}:{rec.get('port','?')}"
        )
    print("\ntypes:", {k: len(v) for k, v in sorted(by_type.items())})
    print("instances:", len(cfg.get("agent_instances") or {}))
    print("cursor in roster:", "cursor" in by_type)

    print("\n=== browser HTTP from Windows Python ===")
    for aid, rec in sorted(agents.items()):
        if not isinstance(rec, dict):
            continue
        at = (rec.get("type") or "").strip()
        if at in ("opencode", "none", "cline"):
            print(f"  {aid}: CLI-only (no browser expected)")
            continue
        port = rec.get("port") or PORT_HINTS.get(aid)
        host = rec.get("host") or "127.0.0.1"
        if not port:
            print(f"  {aid}: no port")
            continue
        path = "/chat" if at == "openclaw" else "/"
        url = f"http://{host}:{port}{path}"
        print(f"  {aid}: {http_code(url)} {url}")

    print("\n=== Windows host CLI ===")
    for c in ("claude", "cursor", "codex", "docker", "hermes", "openclaw", "opencode"):
        print(f"  {c}: {which(c) or 'NOT FOUND'}")

    print("\n=== WSL CLI ===")
    print(wsl("for c in docker hermes openclaw opencode codex claude cursor; do printf '%s: ' $c; command -v $c || echo NOT_FOUND; done"))

    print("\n=== docker exec CLI ===")
    pairs = [
        ("docker-agents-hermes-1", "hermes"),
        ("docker-agents-openclaw-1", "openclaw"),
        ("docker-agents-opencode-1", "opencode"),
        ("docker-agents-codex-web-1", "codex"),
    ]
    for ctn, bin_ in pairs:
        out = wsl(f"docker exec {ctn} command -v {bin_} || echo NOT_FOUND")
        print(f"  {ctn}/{bin_}: {out}")


if __name__ == "__main__":
    main()
