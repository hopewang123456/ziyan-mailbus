#!/usr/bin/env python3
"""Patch store/config.json — per-agent Codex browser/ttyd ports."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from lib.launch_ports import load_launch_port_defaults
from lib.utils import json_read, json_write

_defaults = load_launch_port_defaults()
CODEX_PORTS = {}
for agent_id, web_port in (_defaults.get("codex_web") or {}).items():
    if str(agent_id).startswith("_"):
        continue
    ttyd = (_defaults.get("codex_ttyd") or {}).get(agent_id)
    entry = {"web_port": str(web_port), "url": "http://127.0.0.1:{port}/"}
    if ttyd:
        entry["ttyd_url"] = f"http://127.0.0.1:{ttyd}/"
    CODEX_PORTS[agent_id] = entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data-dir",
        default=os.environ.get("DATA_DIR") or os.path.join(ROOT, "store"),
    )
    args = ap.parse_args()
    path = os.path.join(os.path.abspath(args.data_dir), "config.json")
    cfg = json_read(path, {})
    agents = cfg.get("agents") or {}
    changed = False
    for name, ports in CODEX_PORTS.items():
        if name not in agents:
            continue
        launch = agents[name].setdefault("launch", {})
        browser = launch.setdefault("browser", {})
        for key, val in ports.items():
            if browser.get(key) != val:
                browser[key] = val
                changed = True
        browser.setdefault("url", "http://127.0.0.1:{port}/")
        browser.setdefault("kind", "codex_docker")
        launch.setdefault("launch_via_api", True)
        launch.setdefault("has_browser", True)
        launch.setdefault("template", "codex_docker")
        if changed:
            print(f"  {name} -> {ports}")
    if changed:
        json_write(path, cfg)
        print(f"patched {path}")
    else:
        print("no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
