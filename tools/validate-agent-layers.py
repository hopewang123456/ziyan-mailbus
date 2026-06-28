#!/usr/bin/env python3
"""Validate L0–L2 agent layer specs and detect forbidden inline duplication."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.framework_skills import AGENT_ARCHETYPES, layer_skills_for_agent  # noqa: E402

INDEX = ROOT / "store" / "agents" / "json" / "skills-index.json"
IDENTITIES = ROOT / "identities"
ORG_OVERLAYS = ROOT / "org"
OPENCODE_AGENTS = ROOT.parent / "opencode" / "AGENTS.md"
SKILLS_COMMON = ROOT / "skills" / "common"
ADAPTERS_SHARED = ROOT / "adapters" / "_shared"


def _protocol_skill_path() -> Path:
    v3 = SKILLS_COMMON / "mailbus-file-protocol" / "SKILL.md"
    if v3.is_file():
        return v3
    return ADAPTERS_SHARED / "mailbus-file-protocol" / "SKILL.md"


def _universal_skill_path() -> Path:
    v3 = SKILLS_COMMON / "agent-universal" / "SKILL.md"
    if v3.is_file():
        return v3
    return ADAPTERS_SHARED / "agent-universal" / "SKILL.md"


MAILBUS_FILE_PROTOCOL = _protocol_skill_path()

FORBIDDEN_IDENTITY_PATTERNS = [
    re.compile(r"##\s*📬\s*mailbus", re.I),
    re.compile(r"收到消息后必须做", re.I),
    re.compile(r"写 ack 确认已读", re.I),
]

DELIVERY_TABLE_IN_L0 = re.compile(
    r"\|\s*opencode\s*\(dali\)\s*\|",
    re.I,
)


def _load_index() -> dict:
    if not INDEX.is_file():
        return {}
    return json.loads(INDEX.read_text(encoding="utf-8"))


def check_skills_index(index: dict) -> list[str]:
    errors: list[str] = []
    agents = index.get("agents") or {}
    for agent_id, archetype in AGENT_ARCHETYPES.items():
        entry = agents.get(agent_id)
        if not entry:
            errors.append(f"skills-index: missing agent {agent_id}")
            continue
        fw = (entry.get("framework") or "").strip()
        if not fw:
            errors.append(f"skills-index: {agent_id} missing framework")
            continue
        expected = layer_skills_for_agent(agent_id, fw)
        expected_ids = [s["id"] for s in expected]
        skills = entry.get("skills") or []
        actual_ids = [s.get("id") for s in skills[: len(expected_ids)] if isinstance(s, dict)]
        if actual_ids != expected_ids:
            errors.append(
                f"skills-index: {agent_id} layer order mismatch\n"
                f"  expected prefix: {expected_ids}\n"
                f"  actual prefix:   {actual_ids}"
            )
    return errors


def check_identities() -> list[str]:
    errors: list[str] = []
    for path in IDENTITIES.glob("*.md"):
        if path.name in ("README.md",) or ".draft" in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        agent = path.stem
        for pat in FORBIDDEN_IDENTITY_PATTERNS:
            if pat.search(text):
                errors.append(f"identity {path.name}: forbidden inline mailbus content")
                break
        if agent in AGENT_ARCHETYPES and "mail/skills/roles/overlays/" not in text:
            errors.append(f"identity {path.name}: missing overlay pointer")
    return errors


def check_l0_no_delivery_table() -> list[str]:
    errors: list[str] = []
    if MAILBUS_FILE_PROTOCOL.is_file():
        text = MAILBUS_FILE_PROTOCOL.read_text(encoding="utf-8")
        if DELIVERY_TABLE_IN_L0.search(text):
            errors.append("mailbus-file-protocol SKILL.md: framework delivery table must not be in L0")
    if OPENCODE_AGENTS.is_file():
        text = OPENCODE_AGENTS.read_text(encoding="utf-8")
        if "msg-results 为任务完成依据" in text or "msg-results/{msg_id}.json` 为任务完成" in text:
            errors.append("opencode/AGENTS.md: dali must use patch+replies SoT, not msg-results primary")
        if "## 📬 mailbus" in text:
            errors.append("opencode/AGENTS.md: mailbus rules must be in L0/L1 skills only")
    return errors


def check_role_files_exist() -> list[str]:
    errors: list[str] = []
    for agent_id, archetype in AGENT_ARCHETYPES.items():
        arch_v3 = ROOT / "skills" / "roles" / "archetypes" / archetype / "SKILL.md"
        arch_legacy = ROOT / "roles" / "archetypes" / archetype / "SKILL.md"
        overlay_v3 = ROOT / "skills" / "roles" / "overlays" / agent_id / "SKILL.md"
        overlay_legacy = ROOT / "roles" / "overlays" / agent_id / "SKILL.md"
        if not arch_v3.is_file() and not arch_legacy.is_file():
            errors.append(f"missing archetype skill: {arch_v3} (or legacy {arch_legacy})")
        if not overlay_v3.is_file() and not overlay_legacy.is_file():
            errors.append(f"missing overlay skill: {overlay_v3} (or legacy {overlay_legacy})")
    universal = _universal_skill_path()
    if not universal.is_file():
        errors.append(f"missing L0: {universal}")
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description="Validate agent layer specs")
    p.add_argument("--check", action="store_true", help="Exit 2 on violations (default)")
    args = p.parse_args()

    errors: list[str] = []
    errors.extend(check_role_files_exist())
    errors.extend(check_l0_no_delivery_table())
    errors.extend(check_identities())
    index = _load_index()
    if index:
        errors.extend(check_skills_index(index))
    else:
        print("WARN: skills-index.json not found, skipping index checks", file=sys.stderr)

    if errors:
        for e in errors:
            print("FAIL", e, file=sys.stderr)
        return 2
    print("OK: agent layers validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
