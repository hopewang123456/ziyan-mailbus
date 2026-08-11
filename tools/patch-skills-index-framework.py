#!/usr/bin/env python3
"""幂等补全 skills-index 的 L0–L2 layer skills（v3: access/**/agent.json SoT）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.adapters.config.agent_registry import load_all_agents  # noqa: E402
from lib.adapters.config.sync_layers import build_skills_index_from_registry  # noqa: E402

INDEX = ROOT / "store" / "agents" / "json" / "skills-index.json"


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def patch_index(*, check_only: bool = False, data_dir: str | None = None) -> tuple[list[str], list[str]]:
    existing = _load_json(INDEX)
    registry = load_all_agents(refresh=True)
    if not registry:
        return [], ["no agents in access/transport/**/transport.json"]

    new_index = build_skills_index_from_registry(existing_index=existing)
    changes: list[str] = []
    errors: list[str] = []

    old_agents = existing.get("agents") or {}
    new_agents = new_index.get("agents") or {}

    for agent_id in sorted(registry):
        if agent_id not in new_agents:
            errors.append(f"{agent_id}: missing from built index")
            continue
        old_skills = (old_agents.get(agent_id) or {}).get("skills") or []
        new_skills = new_agents[agent_id].get("skills") or []
        if old_skills != new_skills:
            changes.append(f"{agent_id}: refresh L0–L2 from profile ({registry[agent_id].get('framework')})")
        old_fw = (old_agents.get(agent_id) or {}).get("framework")
        new_fw = new_agents[agent_id].get("framework")
        if old_fw != new_fw and f"{agent_id}: refresh" not in changes:
            changes.append(f"{agent_id}: framework {old_fw!r} → {new_fw!r}")

    if not check_only and changes:
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps(new_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return changes, errors


def main() -> int:
    p = argparse.ArgumentParser(description="Patch skills-index from access/**/agent.json")
    p.add_argument("--check", action="store_true", help="只检查，不写文件")
    p.add_argument("--data-dir", default=str(ROOT / "store"), help="runtime store (for future use)")
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
