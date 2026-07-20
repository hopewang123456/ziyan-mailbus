#!/usr/bin/env python3
"""CLI：mailbus external-tools 目录（registry / grants / adapters）。"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.external_tools import (
    external_tools_dir,
    invoke_tool,
    list_adapters_for_agent,
    list_tools_for_agent,
    load_external_tools_config,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="mailbus external-tools")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出某 agent 可用 tools（含 adapter 摘要）")
    p_list.add_argument("--agent", required=True)

    p_adapters = sub.add_parser("list-adapters", help="列出某 agent 全部 adapter 文件")
    p_adapters.add_argument("--agent", required=True)

    p_invoke = sub.add_parser("invoke", help="调用 tool")
    p_invoke.add_argument("--agent", required=True)
    p_invoke.add_argument("--tool", required=True)
    p_invoke.add_argument("--inputs", default="{}", help="JSON 字符串")
    p_invoke.add_argument("--dry-run", action="store_true")

    p_cfg = sub.add_parser("show-config", help="打印 external-tools 目录与加载状态")

    args = ap.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_tools_for_agent(args.data_dir, args.agent), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "list-adapters":
        print(json.dumps(list_adapters_for_agent(args.data_dir, args.agent), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "invoke":
        inputs = json.loads(args.inputs)
        out = invoke_tool(
            args.data_dir,
            agent_id=args.agent,
            tool_id=args.tool,
            inputs=inputs,
            dry_run=args.dry_run,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") or out.get("dry_run") else 1

    if args.cmd == "show-config":
        cfg = load_external_tools_config(args.data_dir)
        print(
            json.dumps(
                {
                    "external_tools_dir": external_tools_dir(args.data_dir),
                    "tools": len(cfg.get("tools") or []),
                    "agents": list((cfg.get("agent_grants") or {}).keys()),
                    "paths": cfg.get("_paths"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
