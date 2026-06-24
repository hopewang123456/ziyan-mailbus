"""Framework runtime skill paths — shared by patch + sync scripts."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "adapters"
ROLES = ROOT / "roles"

FRAMEWORK_SKILL_DIRS: dict[str, str] = {
    "hermes": "hermes/framework-runtime/SKILL.md",
    "hermes_profile": "hermes_profile/framework-runtime/SKILL.md",
    "opencode": "opencode/framework-runtime/SKILL.md",
    "codex": "codex/framework-runtime/SKILL.md",
    "claude_code": "claude_code/framework-runtime/SKILL.md",
    "openclaw": "openclaw/framework-runtime/SKILL.md",
    "cline": "cline/framework-runtime/SKILL.md",
    "cursor": "cursor/framework-runtime/SKILL.md",
}

SHARED_PROTOCOL = "_shared/mailbus-file-protocol/SKILL.md"
AGENT_UNIVERSAL = "_shared/agent-universal/SKILL.md"

AGENT_ARCHETYPES: dict[str, str] = {
    "dali": "coding-executor",
    "lingyun": "coding-pro",
    "lingyan": "test-engineer",
    "lingjian": "code-reviewer",
    "lingzhao": "spec-designer",
    "xiaoqi": "orchestrator",
    "yige": "operations",
    "lingjin": "security-auditor",
    "lingxi": "tech-radar",
    "lingtuo": "market-expansion",
    "lingxun": "patroller",
    "lingxiao": "tech-lead",
    "lingzhang": "finance-followup",
}

# hermes_profile 编制（与 docker entrypoint 一致）
HERMES_PROFILE_AGENTS: tuple[str, ...] = (
    "lingzhao",
    "lingjin",
    "lingxi",
    "lingtuo",
    "lingxun",
    "lingzhang",
)


def hermes_sync_skills_dir(agent_id: str, *, mail_root: Path | None = None) -> Path:
    """宿主机 / 容器内 Hermes L0–L2 skills 同步目标。"""
    root = mail_root or ROOT
    return root / "adapters" / ".sync" / agent_id / "skills"


def framework_skill_id(framework: str) -> str:
    return f"framework-runtime-{framework.replace('_', '-')}"


def framework_skill_path_rel(framework: str) -> str:
    rel = FRAMEWORK_SKILL_DIRS.get(framework)
    if not rel:
        raise ValueError(f"unknown framework: {framework}")
    return f"mail/adapters/{rel}"


def universal_skill_spec() -> dict:
    return {
        "id": "agent-universal",
        "path": f"mail/adapters/{AGENT_UNIVERSAL}",
        "type": "shared_skill",
        "layer": "L0",
        "always": True,
    }


def shared_protocol_spec() -> dict:
    return {
        "id": "mailbus-file-protocol",
        "path": f"mail/adapters/{SHARED_PROTOCOL}",
        "type": "shared_skill",
        "layer": "L0",
        "always": True,
    }


def framework_skill_spec(framework: str) -> dict:
    return {
        "id": framework_skill_id(framework),
        "path": framework_skill_path_rel(framework),
        "type": "framework_skill",
        "layer": "L1",
        "framework": framework,
        "always": True,
    }


def role_archetype_spec(agent_id: str) -> dict:
    archetype = AGENT_ARCHETYPES.get(agent_id)
    if not archetype:
        raise ValueError(f"unknown agent for archetype: {agent_id}")
    return {
        "id": f"role-{archetype}",
        "path": f"mail/roles/archetypes/{archetype}/SKILL.md",
        "type": "role_archetype",
        "layer": "L2",
        "archetype": archetype,
        "always": True,
    }


def role_overlay_spec(agent_id: str) -> dict:
    if agent_id not in AGENT_ARCHETYPES:
        raise ValueError(f"unknown agent for overlay: {agent_id}")
    return {
        "id": f"role-overlay-{agent_id}",
        "path": f"mail/roles/overlays/{agent_id}/SKILL.md",
        "type": "role_overlay",
        "layer": "L2",
        "agent_id": agent_id,
        "extends": AGENT_ARCHETYPES[agent_id],
        "always": True,
    }


def layer_skills_for_agent(agent_id: str, framework: str) -> list[dict]:
    """Ordered L0–L2 specs for one agent."""
    return [
        universal_skill_spec(),
        shared_protocol_spec(),
        framework_skill_spec(framework),
        role_archetype_spec(agent_id),
        role_overlay_spec(agent_id),
    ]


def resolve_skill_src(rel: str, *, mail_root: Path | None = None) -> Path:
    """Resolve mail/adapters/... mail/roles/... or .codex/... paths from repo root."""
    mail_root = mail_root or ROOT
    ai_tools = mail_root.parent
    rel = (rel or "").replace("\\", "/")
    if rel.startswith("mail/adapters/"):
        return mail_root / rel.replace("mail/", "", 1)
    if rel.startswith("mail/roles/"):
        return mail_root / rel.replace("mail/", "", 1)
    if rel.startswith(".codex/"):
        return ai_tools / rel
    if rel.startswith("store/"):
        return mail_root / rel
    p = Path(rel)
    return p if p.is_absolute() else ai_tools / rel


SYNCABLE_SKILL_TYPES = frozenset({
    "codex_skill",
    "framework_skill",
    "shared_skill",
    "role_archetype",
    "role_overlay",
})


def install_skill_spec(
    spec: dict,
    skills_root: Path,
    *,
    mail_root: Path | None = None,
    use_symlink: bool = True,
) -> bool:
    """Copy or symlink one skill entry into skills_root/{id}/SKILL.md."""
    import shutil

    stype = spec.get("type") or ""
    if stype not in SYNCABLE_SKILL_TYPES:
        return False
    rel = spec.get("path") or ""
    sid = spec.get("id") or Path(rel).stem
    if not rel.endswith("SKILL.md"):
        return False
    src = resolve_skill_src(rel, mail_root=mail_root)
    if not src.is_file():
        return False
    dest_dir = skills_root / sid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_skill = dest_dir / "SKILL.md"
    if use_symlink:
        try:
            if dest_skill.is_symlink() or dest_skill.exists():
                dest_skill.unlink()
            rel_target = os.path.relpath(src.resolve(), dest_dir.resolve())
            dest_skill.symlink_to(rel_target)
            return True
        except OSError:
            pass
    shutil.copy2(src, dest_skill)
    return True


def sync_agent_skills_from_index(
    agent: str,
    skills_root: Path,
    index: dict,
    *,
    mail_root: Path | None = None,
    use_symlink: bool = True,
) -> list[str]:
    """Sync all index skills for agent; returns installed skill ids."""
    entry = (index.get("agents") or {}).get(agent) or {}
    installed: list[str] = []
    for spec in entry.get("skills") or []:
        if not isinstance(spec, dict):
            continue
        if install_skill_spec(spec, skills_root, mail_root=mail_root, use_symlink=use_symlink):
            installed.append(spec.get("id") or "")
    return installed
