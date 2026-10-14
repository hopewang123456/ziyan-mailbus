#!/usr/bin/env python3
"""Align agent cards + add cursor; restart Claude ttyd / Codex gateway."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "store" / "config.json"
sys.path.insert(0, str(ROOT / "python"))


def main() -> int:
    from lib.adapters.config.agent_instances import synthesize_instances_from_agents
    from lib.adapters.frameworks.claude_browser_launch import ensure_claude_web

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    agents = cfg.setdefault("agents", {})

    # Claude SoT: launch.browser.web_port / mailbus_claude.browser_ports
    # lingyun=9260, lingyan=9261
    for aid, port in (("lingyun", 9260), ("lingyan", 9261)):
        rec = agents.get(aid) or {}
        rec["port"] = port
        launch = rec.setdefault("launch", {})
        browser = launch.setdefault("browser", {})
        browser["web_port"] = str(port)
        browser.setdefault("kind", "claude_ttyd")
        agents[aid] = rec

    # Codex primary browser = UI (924x); ttyd backup remains 925x
    for aid, ui, ttyd in (("lingxiao", 9240, 9250), ("lingjian", 9241, 9251)):
        rec = agents.get(aid) or {}
        rec["port"] = ui
        launch = rec.setdefault("launch", {})
        browser = launch.setdefault("browser", {})
        browser["port"] = ui
        browser["ttyd_port"] = ttyd
        browser["ttyd_url"] = f"http://127.0.0.1:{ttyd}/"
        agents[aid] = rec

    if "cursor" not in agents:
        agents["cursor"] = {
            "type": "cursor",
            "role": "IDE 宿主",
            "run_target": "windows",
            "host": "127.0.0.1",
            "auth": {"mode": "none", "note": "Cursor IDE/CLI — no browser entry"},
            "launch": {"has_browser": False, "cli": {"kind": "shell"}},
            "available": True,
            "enabled": True,
        }
        print("added cursor agent card")

    cfg["agents"] = agents
    cfg = synthesize_instances_from_agents(cfg)
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("cards patched; instances=", len(cfg.get("agent_instances") or {}))

    print("=== ensure claude ttyd ===")
    for a in ("lingyun", "lingyan"):
        try:
            info = ensure_claude_web(a, str(ROOT / "store"), wait_seconds=30)
            print(a, "OK", info)
        except Exception as e:
            print(a, "FAIL", e)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
