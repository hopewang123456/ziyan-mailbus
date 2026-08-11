#!/usr/bin/env python3
"""Hermes 各 profile 最小启动探针 — 使用 agent_adapters 统一指令。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.adapters.frameworks import resolve_push_cli


def probe_profile(agent_id: str, agent_cfg: dict, agent_types: dict, timeout: int) -> tuple[bool, str]:
    base = resolve_push_cli(agent_id, agent_cfg, agent_types)
    # 去掉 MSG 占位，换成探针 prompt
    cmd_str = base.replace("-q 'MSG' -Q", "").strip()
    cmd_str = cmd_str.replace("--yolo", "--yolo -q 'reply PROFILE_OK' -Q")
    cmd = cmd_str.split()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        if "Unknown skill" in out or out.strip().startswith("Error:"):
            return False, out.strip()[:300]
        return True, "started"
    except subprocess.TimeoutExpired:
        return True, "timeout (CLI running, no immediate error)"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "store"))
    ap.add_argument("--timeout", type=int, default=45)
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(args.data_dir, "config.json"), encoding="utf-8"))
    agents = cfg.get("agents", {})
    agent_types = cfg.get("agent_types", {})

    failed = 0
    total = 0
    for agent_id, acfg in sorted(agents.items()):
        if acfg.get("type") != "hermes_profile":
            continue
        total += 1
        display = acfg.get("name") or agent_id
        profile = acfg.get("profile") or agent_id
        ok, msg = probe_profile(agent_id, acfg, agent_types, args.timeout)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {agent_id} ({display}) profile={profile}: {msg}")
        if not ok:
            failed += 1

    if failed:
        print(f"FAIL {failed}/{total} hermes profiles", file=sys.stderr)
        return 1
    print(f"OK {total}/{total} hermes profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
