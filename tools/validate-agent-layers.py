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

from lib.infra.constants import AGENT_VAULT_ROOT  # noqa: E402
from lib.adapters.config.agent_registry import layer_skills_for_agent, load_all_agents  # noqa: E402


def _agent_archetypes() -> dict[str, str]:
    return {
        aid: str(rec.get("archetype") or "")
        for aid, rec in load_all_agents().items()
        if rec.get("archetype")
    }

INDEX = ROOT / "store" / "agents" / "json" / "skills-index.json"
OPENCODE_AGENTS = ROOT.parent / "opencode" / "AGENTS.md"


def _protocol_skill_path() -> Path:
    return AGENT_VAULT_ROOT / "01-mailbus" / "012-skills" / "0121-common" / "mailbus-file-protocol" / "SKILL.md"


def _universal_skill_path() -> Path:
    return AGENT_VAULT_ROOT / "02-members" / "021-common" / "0211-rules" / "agent-universal" / "SKILL.md"


MAILBUS_FILE_PROTOCOL = _protocol_skill_path()

FORBIDDEN_IDENTITY_PATTERNS = [
    re.compile(r"##\s*📬\s*mailbus", re.I),
    re.compile(r"收到消息后必须做", re.I),
    re.compile(r"写 ack 确认已读", re.I),
]

DELIVERY_TABLE_IN_L0 = re.compile(
    r"\|\s*opencode\s*\(opencode\)\s*\|",
    re.I,
)


def _load_index() -> dict:
    if not INDEX.is_file():
        return {}
    return json.loads(INDEX.read_text(encoding="utf-8"))


def check_skills_index(index: dict) -> list[str]:
    errors: list[str] = []
    agents = index.get("agents") or {}
    for agent_id, archetype in _agent_archetypes().items():
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


def check_l0_no_delivery_table() -> list[str]:
    errors: list[str] = []
    if MAILBUS_FILE_PROTOCOL.is_file():
        text = MAILBUS_FILE_PROTOCOL.read_text(encoding="utf-8")
        if DELIVERY_TABLE_IN_L0.search(text):
            errors.append("mailbus-file-protocol SKILL.md: framework delivery table must not be in L0")
    if OPENCODE_AGENTS.is_file():
        text = OPENCODE_AGENTS.read_text(encoding="utf-8")
        if "msg-results 为任务完成依据" in text or "msg-results/{msg_id}.json` 为任务完成" in text:
            errors.append("opencode/AGENTS.md: opencode agent must use patch+replies SoT, not msg-results primary")
        if "## 📬 mailbus" in text:
            errors.append("opencode/AGENTS.md: mailbus rules must be in L0/L1 skills only")
    return errors


def check_role_files_exist() -> list[str]:
    errors: list[str] = []
    for agent_id, archetype in _agent_archetypes().items():
        fw = str(load_all_agents().get(agent_id, {}).get("framework") or "")
        specs = layer_skills_for_agent(agent_id, fw)
        has_arch = any(s.get("type") == "role_archetype" for s in specs)
        has_overlay = any(s.get("type") == "role_overlay" for s in specs)
        if not has_arch:
            errors.append(f"missing archetype skill for {agent_id} (archetype={archetype})")
        if not has_overlay:
            errors.append(f"missing overlay skill for {agent_id}")
        for spec in specs:
            rel = spec.get("path") or ""
            if not rel:
                continue
            p = _resolve_spec_path(rel)
            if not p.is_file():
                errors.append(f"missing skill file: {p}")
    universal = _universal_skill_path()
    if not universal.is_file():
        errors.append(f"missing L0 agent-universal: {universal}")
    if not MAILBUS_FILE_PROTOCOL.is_file():
        errors.append(f"missing L0 mailbus-file-protocol: {MAILBUS_FILE_PROTOCOL}")
    return errors


def _resolve_spec_path(rel: str) -> Path:
    from lib.adapters.config.agent_registry import resolve_skill_src
    return resolve_skill_src(rel)


def main() -> int:
    p = argparse.ArgumentParser(description="Validate agent layer specs")
    p.add_argument("--check", action="store_true", help="Exit 2 on violations (default)")
    args = p.parse_args()

    errors: list[str] = []
    errors.extend(check_role_files_exist())
    errors.extend(check_l0_no_delivery_table())
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
