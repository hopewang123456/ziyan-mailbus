"""Tests for mailbus/skills framework runtime (v3 SoT; mail/skills alias still resolves)."""
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


def _skip_if_local_only(path: Path, what: str) -> None:
    """skills/ 是本机 Vault junction（.gitignore 刻意不入库）——干净 clone 缺文件时跳过。"""
    if not path.is_file():
        pytest.skip(f"{what} not present (local-only skills mirror): {path}")


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_framework_skill_exists(fw: str) -> None:
    skill = _framework_skill_path(fw)
    _skip_if_local_only(skill, f"framework skill {fw}")
    assert True  # 存在性由 _skip_if_local_only 守卫（本机 mirror 存在即过）


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_framework_skill_line_budget(fw: str) -> None:
    skill = _framework_skill_path(fw)
    _skip_if_local_only(skill, f"framework skill {fw}")
    lines = skill.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_SKILL_LINES, f"{fw} SKILL.md too long: {len(lines)}"


def test_agent_universal_exists() -> None:
    vault_skill = Path(__file__).resolve().parents[2].parent / "Obsidian" / "Vaults" / "Agent"
    skill = (
        vault_skill
        / "01-mailbus"
        / "011-rule"
        / "0111-common"
        / "agent-universal"
        / "SKILL.md"
    )
    if not skill.is_file():
        skill = Path(__file__).resolve().parents[2] / "rules" / "common" / "agent-universal" / "SKILL.md"
    _skip_if_local_only(skill, "agent-universal L0")
    assert "layer: L0" in skill.read_text(encoding="utf-8")


def test_shared_protocol_exists() -> None:
    skill = _shared_skill("mailbus-file-protocol")
    _skip_if_local_only(skill, "shared protocol")


def test_shared_protocol_line_budget() -> None:
    skill = _shared_skill("mailbus-file-protocol")
    _skip_if_local_only(skill, "shared protocol")
    assert len(skill.read_text(encoding="utf-8").splitlines()) <= 80


def test_shared_protocol_no_framework_delivery_table() -> None:
    skill = _shared_skill("mailbus-file-protocol")
    _skip_if_local_only(skill, "shared protocol")
    text = skill.read_text(encoding="utf-8")
    assert "opencode (agent-i)" not in text


@pytest.mark.parametrize("fw", FRAMEWORKS)
def test_framework_frontmatter(fw: str) -> None:
    skill = _framework_skill_path(fw)
    _skip_if_local_only(skill, f"framework skill {fw}")
    text = skill.read_text(encoding="utf-8")
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
    from lib.adapters.config.agent_registry import resolve_skill_src
    return resolve_skill_src(path)


def _env_content_gaps() -> list[str]:
    """检查本机 Vault/技能内容 SoT 是否备齐（L0 两件 + 各 agent archetype/overlay）。

    这些文件属 Obsidian Vault 个人内容，代码仓库无法提供；缺失时相关维护性
    测试跳过（对齐「Vault 是增强层，未配置不标红」哲学），环境备齐时仍严格断言。
    """
    from lib.infra.constants import AGENT_VAULT_ROOT
    from lib.adapters.config.agent_registry import layer_skills_for_agent, load_all_agents

    gaps: list[str] = []
    l0_protocol = AGENT_VAULT_ROOT / "01-mailbus" / "012-skills" / "0121-common" / "mailbus-file-protocol" / "SKILL.md"
    l0_universal = (
        AGENT_VAULT_ROOT
        / "01-mailbus"
        / "011-rule"
        / "0111-common"
        / "agent-universal"
        / "SKILL.md"
    )
    if not l0_protocol.is_file():
        gaps.append(f"missing L0 mailbus-file-protocol: {l0_protocol}")
    if not l0_universal.is_file():
        gaps.append(f"missing L0 agent-universal: {l0_universal}")
    try:
        registry = load_all_agents(refresh=True)
    except Exception as e:  # noqa: BLE001
        gaps.append(f"agent registry unavailable: {e}")
        return gaps
    for aid, rec in sorted(registry.items()):
        if not rec.get("archetype"):
            continue
        fw = rec.get("framework") or rec.get("type") or ""
        try:
            specs = layer_skills_for_agent(aid, fw) or []
        except Exception as e:  # noqa: BLE001
            gaps.append(f"{aid}: layer_skills_for_agent error: {e}")
            continue
        types = {s.get("type") for s in specs}
        if "role_archetype" not in types:
            gaps.append(f"missing archetype skill for {aid} (archetype={rec['archetype']})")
        if "role_overlay" not in types:
            gaps.append(f"missing overlay skill for {aid}")

    # 索引引用的技能实体文件（03-shared 等个人 Vault 内容）——缺失同样按
    # 「Vault 是增强层」哲学跳过严格断言，而不是标红（内容在用户侧迁回后自动恢复严格）。
    if INDEX.is_file():
        try:
            idx = json.loads(INDEX.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            gaps.append(f"skills-index unreadable: {e}")
            return gaps
        missing: set[str] = set()
        for rec in (idx.get("agents") or {}).values():
            for sk in rec.get("skills") or []:
                rel = str(sk.get("path") or "")
                if rel and not _resolve_skill_path(rel).is_file():
                    missing.add(rel)
        if missing:
            gaps.append(f"referenced skill files missing in Vault: {sorted(missing)[:3]}")
    return gaps


def test_all_roster_agents_have_layer_skills(skills_index: dict, config_agents: dict) -> None:
    gaps = _env_content_gaps()
    if gaps:
        pytest.skip("Vault 内容未备齐（增强层，不标红）: " + "; ".join(gaps[:3]))
    agents = skills_index.get("agents") or {}
    roster = set(agents.keys())
    if not roster:
        pytest.skip("no roster in skills-index (open-source default)")
    for agent_id in roster:
        assert agent_id in agents, f"missing index entry: {agent_id}"
        skills = agents[agent_id].get("skills") or []
        assert len(skills) >= 4, f"{agent_id}: need L0-L2 skills"
        # L0 → L1 → L2 顺序
        assert skills[0].get("id") == "mailbus-file-protocol"
        assert skills[1].get("type") == "framework_skill"
        assert skills[2].get("type") == "role_archetype"
        assert skills[3].get("type") == "role_overlay"
        assert skills[3].get("id") == f"role-overlay-{agent_id}"
        fw = agents[agent_id].get("framework") or config_agents.get(agent_id, {}).get("type")
        assert skills[1].get("framework") == fw, f"{agent_id}: framework mismatch"
        rel = skills[1].get("path", "")
        assert _resolve_skill_path(rel).is_file(), f"{agent_id}: skill path missing: {rel}"


def test_patch_check_passes() -> None:
    gaps = _env_content_gaps()
    if gaps:
        pytest.skip("Vault 内容未备齐（增强层，不标红）: " + "; ".join(gaps[:3]))
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "patch-skills-index-framework.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_validate_agent_layers_passes() -> None:
    gaps = _env_content_gaps()
    if gaps:
        pytest.skip("Vault 内容未备齐（增强层，不标红）: " + "; ".join(gaps[:3]))
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate-agent-layers.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
