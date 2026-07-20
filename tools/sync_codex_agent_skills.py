#!/usr/bin/env python3
"""Codex skills-index → CODEX_HOME/skills 同步（供 sync-codex-agent-skills.sh 调用）。"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ.get("MAILBUS_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))

AGENT = os.environ.get("CODEX_AGENT", "").strip()
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or "/home/node/.codex")
DATA_DIR = Path(os.environ.get("DATA_DIR") or ROOT / "store")
SKILLS_ROOT = CODEX_HOME / "skills"
AI_TOOLS = ROOT.parent


def resolve(rel: str) -> Path:
    rel = (rel or "").replace("\\", "/")
    if rel.startswith(".codex/"):
        return AI_TOOLS / rel
    if rel.startswith("store/"):
        return ROOT / rel
    p = Path(rel)
    return p if p.is_absolute() else AI_TOOLS / rel


def _host_codex_sync_blocked(codex_home: Path) -> str | None:
    """Codex sync targets container CODEX_HOME; skip on WSL/Windows host."""
    raw = str(codex_home).replace("\\", "/")
    if raw.startswith("/home/node"):
        return "container CODEX_HOME on host — use container entrypoint sync"
    parent = codex_home.parent
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return str(exc)
    if not os.access(parent, os.W_OK):
        return f"not writable: {parent}"
    return None


def main() -> int:
    if not AGENT:
        print("[ERROR] CODEX_AGENT required", file=sys.stderr)
        return 1
    blocked = _host_codex_sync_blocked(CODEX_HOME)
    if blocked:
        print(f"[sync-codex-agent-skills] skip agent={AGENT}: {blocked}")
        return 0
    index_path = DATA_DIR / "agents" / "json" / "skills-index.json"
    if not index_path.is_file():
        return 0
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = (index.get("agents") or {}).get(AGENT) or {}
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    for spec in entry.get("skills") or []:
        if not isinstance(spec, dict) or spec.get("type") != "codex_skill":
            continue
        rel = spec.get("path") or ""
        sid = spec.get("id") or Path(rel).stem
        src = resolve(rel)
        if not src.is_file():
            continue
        dest = SKILLS_ROOT / sid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / "SKILL.md")
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
    print(f"[sync-codex-agent-skills] agent={AGENT} skills_root={SKILLS_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
