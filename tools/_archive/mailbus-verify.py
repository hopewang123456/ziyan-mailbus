#!/usr/bin/env python3
"""mailbus 步骤验证 CLI — 供 agent 或 CI 调用。

  python tools/mailbus-verify.py --task-id TASK --step-id STEP
  python tools/mailbus-verify.py --pytest-only --data-dir store
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.task_fsm import read_step_result, step_result_path
from lib.utils import json_read
from lib.verify.runner import run_step_verify
from lib.verify.pytest_runner import run_pytest


def main() -> int:
    ap = argparse.ArgumentParser(description="mailbus step verify")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--task-id")
    ap.add_argument("--step-id")
    ap.add_argument("--pytest-only", action="store_true")
    args = ap.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    vc = (cfg.get("mailbus_automation") or {}).get("verify") or {}
    repo = vc.get("repo_root") or os.path.dirname(data_dir)

    if args.pytest_only:
        ok, summary = run_pytest(repo, vc.get("pytest_targets") or ["tests"])
        print(summary)
        return 0 if ok else 1

    if not args.task_id or not args.step_id:
        print("need --task-id and --step-id", file=sys.stderr)
        return 2

    path = step_result_path(data_dir, args.task_id, args.step_id)
    if not os.path.isfile(path):
        print(json.dumps({"ok": False, "error": "result_not_found", "path": path}))
        return 1
    result = json_read(path, {})
    rt = result.get("role_type")
    conclusion = result.get("conclusion") or "done"
    ok, err, meta = run_step_verify(rt, conclusion, result, config=cfg, data_dir=data_dir)
    out = {"ok": ok, "error": err, "meta": meta}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
