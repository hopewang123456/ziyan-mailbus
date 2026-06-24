#!/usr/bin/env python3
"""Codex skills-index → CODEX_HOME/skills 同步（供 sync-codex-agent-skills.sh 调用）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("MAILBUS_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))

from lib.framework_skills import sync_agent_skills_from_index  # noqa: E402

AGENT = os.environ.get("CODEX_AGENT", "").strip()
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or "/home/node/.codex")
DATA_DIR = Path(os.environ.get("DATA_DIR") or ROOT / "store")
SKILLS_ROOT = CODEX_HOME / "skills"


def main() -> int:
    if not AGENT:
        print("[ERROR] CODEX_AGENT required", file=sys.stderr)
        return 1
    index_path = DATA_DIR / "agents" / "json" / "skills-index.json"
    if not index_path.is_file():
        return 0
    index = json.loads(index_path.read_text(encoding="utf-8"))
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    installed = sync_agent_skills_from_index(AGENT, SKILLS_ROOT, index, mail_root=ROOT, use_symlink=False)
    mem_dir = SKILLS_ROOT / f"{AGENT}-memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    skill_md = mem_dir / "SKILL.md"
    if not skill_md.is_file():
        skill_md.write_text(
            f"# {AGENT} memory\n\nCodex 本地记忆快照（render-codex-config / sync 刷新 output.md）。\n",
            encoding="utf-8",
        )
    out = mem_dir / "output.md"
    if not out.is_file():
        out.write_text("# 记忆快照\n\n（暂无）\n", encoding="utf-8")
    print(f"[sync-codex-agent-skills] agent={AGENT} skills_root={SKILLS_ROOT} installed={len(installed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
