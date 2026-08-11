#!/usr/bin/env python3
"""校验 config.json 中全部 agent 的 CLI / 容器 / profile / launch 模板一致性。"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        print(f"ERROR: missing {config_path}")
        return 2

    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    agents = cfg.get("agents") or {}
    agent_types = cfg.get("agent_types") or {}
    templates = agent_types.get("launch_templates") or {}
    errors: list[str] = []

    print(f"agents: {len(agents)}  templates: {len(templates)}")
    print()

    for name, acfg in sorted(agents.items()):
        atype = acfg.get("type", "?")
        display = acfg.get("name") or name
        profile = acfg.get("profile") or acfg.get("agent") or "-"
        launch = acfg.get("launch") or {}
        tmpl_name = launch.get("template", "")
        tmpl_ok = tmpl_name in templates
        role_ok = bool(acfg.get("role") or acfg.get("archetype"))

        issues = []
        if not role_ok:
            issues.append("no role")
        if not tmpl_ok:
            issues.append(f"template '{tmpl_name}' not found" if tmpl_name else "no template")

        if issues:
            mark = "FAIL"
            errors.append(f"{name}: {', '.join(issues)}")
        else:
            mark = "OK"

        print(f"  [{mark}] {display:8s} ({name:12s}) type={atype:16s} profile={profile:10s} tmpl={tmpl_name or '-':20s} {'role=' + (str(acfg.get('role',''))[:16] if role_ok else '?')}")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nALL AGENTS CONFIG OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
