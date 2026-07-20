#!/usr/bin/env python3
"""校验 config.json 中全部 agent 的 CLI / 容器 / profile 一致性。"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.agent_config import validate_agents


def main() -> int:
    ap = argparse.ArgumentParser(description="校验全部 agent 配置")
    ap.add_argument(
        "--data-dir",
        default=os.environ.get("DATA_DIR", "store"),
        help="mailbus store 目录",
    )
    args = ap.parse_args()
    config_path = os.path.join(os.path.abspath(args.data_dir), "config.json")
    if not os.path.isfile(config_path):
        print(f"ERROR: missing {config_path}", file=sys.stderr)
        return 2

    cfg = json.load(open(config_path, encoding="utf-8"))
    agents = cfg.get("agents") or {}
    errors = validate_agents(agents, cfg.get("agent_types") or {})

    print(f"agents checked: {len(agents)}")
    for name, acfg in sorted(agents.items()):
        atype = acfg.get("type", "?")
        display = acfg.get("name") or name
        profile = acfg.get("profile") or acfg.get("agent") or "-"
        ok = not any(name in e for e in errors)
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] {name} ({display}) type={atype} profile={profile}")

    if errors:
        print("\nERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("ALL AGENTS CONFIG OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
