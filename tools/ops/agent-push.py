#!/usr/bin/env python3
"""统一 agent 非交互 push（Python subprocess argv，跨 Windows / macOS / Linux）。

用法:
  python tools/ops/agent-push.py --agent lingyun --data-dir store --prompt "任务正文"
  python tools/ops/agent-push.py --agent lingxiao --data-dir store --prompt "任务正文"
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from lib.agent_push import run_push_direct, try_build_push_direct  # noqa: E402
from lib.utils import json_read  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Mailbus agent push (Python launcher)")
    ap.add_argument("--agent", required=True)
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--model-alias", default="")
    ap.add_argument("--pipeline", action="store_true")
    ap.add_argument("--no-wait", action="store_true", help="仅拉起进程，不等待结束")
    args = ap.parse_args()

    dd = os.path.abspath(args.data_dir)
    cfg = json_read(os.path.join(dd, "config.json"), {})
    agents = cfg.get("agents") or {}
    agent_cfg = agents.get(args.agent) or {}
    if not agent_cfg:
        print(f"[agent-push] unknown agent: {args.agent}", file=sys.stderr)
        return 2

    model_alias = (args.model_alias or "").strip() or None
    if not model_alias:
        models = agent_cfg.get("models") or []
        model_alias = models[0] if models else None

    spec = try_build_push_direct(
        args.agent,
        agent_cfg,
        cfg.get("agent_types") or {},
        data_dir=dd,
        prompt=args.prompt,
        model_name=model_alias,
        pipeline=args.pipeline,
    )
    if not spec:
        print(
            f"[agent-push] direct push not available for type={agent_cfg.get('type')}",
            file=sys.stderr,
        )
        return 2

    return run_push_direct(spec, wait=not args.no_wait)


if __name__ == "__main__":
    raise SystemExit(main())
