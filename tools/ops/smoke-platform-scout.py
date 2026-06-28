#!/usr/bin/env python3
"""platform-scout smoke — 配置校验 + 可选 live 抓取。"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.utils import json_read


def _load_scout():
    path = os.path.join(ROOT, "tools", "platform-scout.py")
    spec = importlib.util.spec_from_file_location("platform_scout", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--live", action="store_true", help="实际请求 v2ex RSS")
    args = ap.parse_args()

    cfg_path = os.path.join(args.data_dir, "config", "leads-sources.json")
    if not os.path.isfile(cfg_path):
        print(f"FAIL  missing {cfg_path}")
        return 1

    cfg = json_read(cfg_path, {})
    enabled = [p.get("id") for p in (cfg.get("platforms") or []) if p.get("enabled")]
    print(f"PASS  leads-sources.json platforms={enabled}")

    routing = cfg.get("routing") or {}
    if routing.get("high_score_threshold") != 75:
        print(f"WARN  high_score_threshold={routing.get('high_score_threshold')} (expected 75)")
    if routing.get("auto_notify_lingzhao_above") != 85:
        print(f"WARN  auto_notify_lingzhao_above={routing.get('auto_notify_lingzhao_above')} (expected 85)")

    intake_path = os.path.join(args.data_dir, "leads", "order-intake.json")
    if not os.path.isfile(intake_path):
        print(f"WARN  missing {intake_path} (create empty array for Phase1)")
    else:
        intake = json_read(intake_path, [])
        print(f"PASS  order-intake.json entries={len(intake) if isinstance(intake, list) else '?'}")

    if not args.live:
        print("PASS  offline smoke (use --live for RSS fetch)")
        return 0

    mod = _load_scout()
    stats = mod.run_scout(args.data_dir, platform_id="v2ex", dry_run=False)
    v2ex = (stats.get("platforms") or {}).get("v2ex") or {}
    count = v2ex.get("count", 0)
    if count <= 0:
        print("FAIL  v2ex live scout returned 0 items")
        return 1
    print(f"PASS  v2ex live items={count} path={v2ex.get('path', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
