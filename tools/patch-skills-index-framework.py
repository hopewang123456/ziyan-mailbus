#!/usr/bin/env python3
"""幂等补全 skills-index 的 L0–L2 layer skills。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.framework_skills import (  # noqa: E402
    AGENT_ARCHETYPES,
    layer_skills_for_agent,
)

INDEX = ROOT / "store" / "agents" / "json" / "skills-index.json"
CONFIG = ROOT / "store" / "config.json"

ROSTER_DEFAULT_TYPES: dict[str, str] = {
    "lingzhao": "hermes_profile",
    "lingjin": "hermes_profile",
    "lingxi": "hermes_profile",
    "lingtuo": "hermes_profile",
    "lingxun": "hermes_profile",
    "lingzhang": "hermes_profile",
    "lingjian": "codex",
    "lingxiao": "codex",
    "lingyan": "claude_code",
    "lingyun": "claude_code",
    "dali": "opencode",
    "xiaoqi": "openclaw",
    "yige": "openclaw",
}

LAYER_TYPES = frozenset({
    "shared_skill",
    "framework_skill",
    "role_archetype",
    "role_overlay",
})


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def agent_framework(agent_id: str, config: dict, index: dict) -> str:
    agents_cfg = config.get("agents") or {}
    if agent_id in agents_cfg:
        return (agents_cfg[agent_id].get("type") or "").strip()
    entry = (index.get("agents") or {}).get(agent_id) or {}
    fw = (entry.get("framework") or "").strip()
    if fw:
        return fw
    return ROSTER_DEFAULT_TYPES.get(agent_id, "")


def _skill_key(spec: dict) -> str:
    return f"{spec.get('type')}:{spec.get('id')}"


def _ordered_skills(existing: list, agent_id: str, framework: str) -> list:
    layer_specs = layer_skills_for_agent(agent_id, framework)
    layer_keys = {_skill_key(s) for s in layer_specs}
    rest = []
    for item in existing or []:
        if not isinstance(item, dict):
            continue
        k = _skill_key(item)
        if k in layer_keys:
            continue
        if item.get("type") in LAYER_TYPES:
            continue
        rest.append(item)
    return layer_specs + rest


def patch_index(*, check_only: bool = False) -> tuple[list[str], list[str]]:
    config = _load_json(CONFIG)
    index = _load_json(INDEX)
    agents = index.setdefault("agents", {})
    errors: list[str] = []
    changes: list[str] = []

    agent_ids = sorted(
        set(ROSTER_DEFAULT_TYPES)
        | set(AGENT_ARCHETYPES)
        | set(agents.keys())
        | set((config.get("agents") or {}).keys())
    )

    for agent_id in agent_ids:
        fw = agent_framework(agent_id, config, index)
        if not fw:
            errors.append(f"{agent_id}: 无法解析 framework type")
            continue
        if agent_id not in AGENT_ARCHETYPES:
            errors.append(f"{agent_id}: 无 AGENT_ARCHETYPES 映射")
            continue
        entry = agents.setdefault(agent_id, {})
        entry["framework"] = fw
        entry["archetype"] = AGENT_ARCHETYPES[agent_id]
        old_skills = entry.get("skills") or []
        new_skills = _ordered_skills(old_skills, agent_id, fw)
        if new_skills != old_skills:
            changes.append(f"{agent_id}: prepend L0–L2 layer skills ({fw})")
            if not check_only:
                entry["skills"] = new_skills

    if not check_only and changes:
        index["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return changes, errors


def main() -> int:
    p = argparse.ArgumentParser(description="Patch skills-index with L0–L2 layer skills")
    p.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = p.parse_args()
    changes, errors = patch_index(check_only=args.check)
    for c in changes:
        print(("NEED " if args.check else "OK ") + c)
    for e in errors:
        print("ERROR", e, file=sys.stderr)
    if errors:
        return 1
    if args.check and changes:
        return 2
    print(f"patched {len(changes)} agent(s)" if changes else "already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
