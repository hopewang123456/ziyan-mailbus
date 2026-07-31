#!/usr/bin/env python3
"""解析 agent CLI — 供 launch-agent.sh 等 shell 脚本调用。"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.adapters.frameworks import resolve_interactive_cli, resolve_push_cli


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", help="agent key，如 lingxi")
    ap.add_argument("--mode", choices=("push", "interactive"), default="interactive")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "store"))
    args = ap.parse_args()

    config_path = os.path.join(os.path.abspath(args.data_dir), "config.json")
    cfg = json.load(open(config_path, encoding="utf-8"))
    agents = cfg.get("agents", {})
    agent_types = cfg.get("agent_types", {})
    agent_cfg = agents.get(args.agent)
    if not agent_cfg:
        print(f"ERROR: unknown agent {args.agent}", file=sys.stderr)
        return 2

    if args.mode == "push":
        print(resolve_push_cli(args.agent, agent_cfg, agent_types))
    else:
        print(resolve_interactive_cli(
            args.agent, agent_cfg, agent_types, data_dir=os.path.abspath(args.data_dir),
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
