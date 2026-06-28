"""Tests for mail/skills framework runtime (v3 SoT)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
INDEX = ROOT / "store" / "agents" / "json" / "skills-index.json"
CONFIG = ROOT / "store" / "config.json"

FRAMEWORKS = (
    "hermes",
    "hermes_profile",
    "opencode",
    "codex",
    "claude_code",
    "openclaw",
    "cline",
    "cursor",
)

MAX_SKILL_LINES = 120
MAX_REF_LINES = 200


def _framework_skill_path(fw: str) -> Path:
    return SKILLS / "frameworks" / fw / "SKILL.md"


def _shared_skill(name: str) -> Path:
    return SKILLS / "common" / name / "SKILL.md"


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_framework_skill_exists(fw: str) -> None:
    skill = _framework_skill_path(fw)
    assert skill.is_file(), f"missing framework skill for {fw}: {skill}"


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_framework_skill_line_budget(fw: str) -> None:
    skill = _framework_skill_path(fw)
    lines = skill.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_SKILL_LINES, f"{fw} SKILL.md too long: {len(lines)}"


def test_agent_universal_exists() -> None:
    skill = _shared_skill("agent-universal")
    assert skill.is_file()
    assert "layer: L0" in skill.read_text(encoding="utf-8")


def test_shared_protocol_exists() -> None:
    skill = _shared_skill("mailbus-file-protocol")
    assert skill.is_file()


def test_shared_protocol_line_budget() -> None:
    skill = _shared_skill("mailbus-file-protocol")
    assert len(skill.read_text(encoding="utf-8").splitlines()) <= 80


def test_shared_protocol_no_framework_delivery_table() -> None:
    text = _shared_skill("mailbus-file-protocol").read_text(encoding="utf-8")
    assert "opencode (dali)" not in text


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_framework_frontmatter(fw: str) -> None:
    text = _framework_skill_path(fw).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "type: framework_skill" in text or fw in ("cline", "cursor")
    assert f"framework: {fw}" in text or fw in ("cline", "cursor")
    assert "layer: L1" in text


_LINK_RE = re.compile(r"\]\(([^)]+)\)")


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_framework_internal_links(fw: str) -> None:
    skill = _framework_skill_path(fw)
    if not skill.is_file():
        pytest.skip(f"no skill for {fw}")
    skill_dir = skill.parent
    text = skill.read_text(encoding="utf-8")
    for match in _LINK_RE.finditer(text):
        href = match.group(1).split("#")[0]
        if not href or href.startswith("http"):
            continue
        target = (skill_dir / href).resolve()
        assert target.is_file(), f"{fw}: broken link {href}"


def test_reference_files_line_budget() -> None:
    if not SKILLS.is_dir():
        pytest.skip("skills/ missing")
    for ref in SKILLS.rglob("references/*.md"):
            n = len(ref.read_text(encoding="utf-8").splitlines())
            assert n <= MAX_REF_LINES, f"{ref} too long: {n}"


@pytest.fixture
def skills_index() -> dict:
    if not INDEX.is_file():
        pytest.skip("skills-index.json not available")
    return json.loads(INDEX.read_text(encoding="utf-8"))


@pytest.fixture
def config_agents() -> dict:
    if not CONFIG.is_file():
        pytest.skip("config.json not available")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    return cfg.get("agents") or {}


def _resolve_skill_path(path: str) -> Path:
    path = path.replace("\\", "/")
    if not path.startswith("mail/skills/"):
        raise AssertionError(f"skills-index must use mail/skills/ paths: {path}")
    return ROOT / path.replace("mail/", "", 1)


def test_all_roster_agents_have_layer_skills(skills_index: dict, config_agents: dict) -> None:
    agents = skills_index.get("agents") or {}
    roster = {
        "lingzhao", "lingjin", "lingxi", "lingtuo", "lingjian", "lingyan",
        "lingxun", "lingxiao", "dali", "xiaoqi", "yige", "lingzhang", "lingyun",
    }
    for agent_id in roster:
        assert agent_id in agents, f"missing index entry: {agent_id}"
        skills = agents[agent_id].get("skills") or []
        assert len(skills) >= 5, f"{agent_id}: need L0-L2 skills"
        assert skills[0].get("id") == "agent-universal"
        assert skills[1].get("id") == "mailbus-file-protocol"
        assert skills[2].get("type") == "framework_skill"
        assert skills[3].get("type") == "role_archetype"
        assert skills[4].get("type") == "role_overlay"
        assert skills[4].get("id") == f"role-overlay-{agent_id}"
        fw = agents[agent_id].get("framework") or config_agents.get(agent_id, {}).get("type")
        assert skills[2].get("framework") == fw, f"{agent_id}: framework mismatch"
        rel = skills[2].get("path", "")
        assert _resolve_skill_path(rel).is_file(), f"{agent_id}: skill path missing: {rel}"


def test_patch_check_passes() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "patch-skills-index-framework.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_validate_agent_layers_passes() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate-agent-layers.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
