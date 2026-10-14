#!/usr/bin/env python3
"""Final verification after topology fixes."""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from shutil import which

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "store" / "config.json"


def code(url: str, timeout: float = 4.0):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"ERR:{type(e).__name__}"


def wsl(cmd: str) -> str:
    r = subprocess.run(
        ["wsl", "-d", "Ubuntu", "-e", "bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (r.stdout or r.stderr or "").strip()


def main() -> None:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    agents = cfg["agents"]
    print("=== cards ===")
    for aid in sorted(agents):
        a = agents[aid]
        print(f"  {aid:10} type={a.get('type'):12} rt={a.get('run_target')} {a.get('host')}:{a.get('port')}")

    print("\n=== browser ===")
    checks = [
        ("hermes lingzhao", "http://127.0.0.1:9120/"),
        ("openclaw xiaoqi", "http://127.0.0.1:18789/"),
        ("codex UI lingxiao", "http://127.0.0.1:9240/"),
        ("codex ttyd", "http://127.0.0.1:9250/"),
        ("codex gw", "http://127.0.0.1:9220/health"),
        ("claude lingyun", "http://127.0.0.1:9260/"),
        ("claude lingyan", "http://127.0.0.1:9261/"),
        ("mailbus", "http://127.0.0.1:9814/api/status"),
    ]
    for name, url in checks:
        print(f"  {name:20} {code(url)} {url}")

    print("\n=== WSL curl claude/gateway ===")
    print(wsl(
        "for u in http://127.0.0.1:9260/ http://127.0.0.1:9261/ http://127.0.0.1:9220/health http://127.0.0.1:9240/; do "
        "c=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 4 $u || echo fail); echo $c $u; done"
    ))

    print("\n=== CLI ===")
    print("  windows claude:", which("claude"))
    print("  windows cursor:", which("cursor"))
    print(wsl(
        "docker exec docker-agents-hermes-1 hermes --version 2>&1 | head -1; "
        "docker exec docker-agents-openclaw-1 openclaw --version 2>&1 | head -1; "
        "docker exec docker-agents-opencode-1 opencode --version 2>&1 | head -1; "
        "docker exec docker-agents-codex-web-1 codex --version 2>&1 | head -1"
    ))


if __name__ == "__main__":
    main()
