#!/usr/bin/env python3
"""Fill portrait/animated paths onto agent cards + restart mailbus lightly."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "shared" / "store" / "config.json"

import sys

sys.path.insert(0, str(ROOT / "python"))
from lib.adapters.config.avatar_paths import ensure_default_portrait_paths


def main() -> None:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    cfg = ensure_default_portrait_paths(cfg)
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for aid, a in (cfg.get("agents") or {}).items():
        p = (a.get("paths") or {}).get("portrait")
        print(aid, "→", p)
    subprocess.run(
        ["wsl", "-d", "Ubuntu", "-e", "bash", "-lc", "docker restart docker-agents-mailbus-1"],
        check=False,
    )
    time.sleep(7)
    with urllib.request.urlopen("http://127.0.0.1:9814/api/avatars/manifest", timeout=10) as r:
        data = json.loads(r.read().decode())
    print("manifest ready", data.get("ready_count"), "/", data.get("count"))
    with urllib.request.urlopen("http://127.0.0.1:9814/api/agent-avatar/lingzhao/portrait", timeout=10) as r:
        print("lingzhao portrait bytes", len(r.read()), r.headers.get("Content-Type"))


if __name__ == "__main__":
    main()
