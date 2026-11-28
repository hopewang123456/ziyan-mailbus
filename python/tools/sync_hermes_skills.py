#!/usr/bin/env python3
"""把 Hermes 各 profile 的共享技能物化为单源生成产物（R2 去重）。

背景：`shared/access/hermes/.sync/<agent>/skills/<skill>/` 原先每个 agent 各存一份
完全相同的 SKILL.md（6 agent × 3 skill = 18 份）。现收敛为单一源：
`shared/access/hermes/.sync/_shared/<skill>/`，需要时用本脚本物化到各 agent。

用法：
  python tools/sync_hermes_skills.py            # 物化默认 6 个 profile
  python tools/sync_hermes_skills.py --agents lingjin lingzhao
  python tools/sync_hermes_skills.py --check     # 只校验不写入，漂移则非 0 退出
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_DIR = REPO_ROOT / "shared" / "access" / "hermes" / ".sync"
SHARED_DIR = SYNC_DIR / "_shared"
DEFAULT_AGENTS = ("lingjin", "lingtuo", "lingxi", "lingxun", "lingzhang", "lingzhao")


def skill_dirs() -> list[Path]:
    return sorted(p for p in SHARED_DIR.iterdir() if p.is_dir())


def sync_agent(agent: str, check: bool) -> list[str]:
    """把 _shared 下的技能目录同步到某 agent；返回不一致项（check 模式）。"""
    drift: list[str] = []
    for skill in skill_dirs():
        dest = SYNC_DIR / agent / "skills" / skill.name
        src_file = skill / "SKILL.md"
        dst_file = dest / "SKILL.md"
        if check:
            if not dst_file.is_file() or not filecmp.cmp(src_file, dst_file, shallow=False):
                drift.append(f"{agent}/{skill.name}")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="物化 Hermes 单源技能到各 profile")
    parser.add_argument("--agents", nargs="+", default=list(DEFAULT_AGENTS))
    parser.add_argument("--check", action="store_true", help="只校验，不写入")
    args = parser.parse_args(argv)

    if not SHARED_DIR.is_dir():
        print(f"缺少单源目录: {SHARED_DIR}", file=sys.stderr)
        return 2

    drift: list[str] = []
    for agent in args.agents:
        drift.extend(sync_agent(agent, args.check))

    if args.check:
        if drift:
            print("技能副本与单源不一致：" + ", ".join(drift), file=sys.stderr)
            return 1
        print(f"技能副本与单源一致（{len(args.agents)} agent）")
        return 0

    print(f"已从单源物化 {len(skill_dirs())} 个技能到 {len(args.agents)} 个 agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
