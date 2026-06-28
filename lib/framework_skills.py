"""Framework runtime skill paths — shared by patch + sync scripts.

SoT: mail/access/**/agent.json via agent_registry + mail/skills/**/SKILL.md.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import agent_registry as _reg
from .constants import MAILBUS_ROOT

ROOT = MAILBUS_ROOT

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


def _load_archetypes() -> dict[str, str]:
    return _reg.agent_archetypes()


AGENT_ARCHETYPES: dict[str, str] = _load_archetypes()


HERMES_PROFILE_AGENTS: tuple[str, ...] = _reg.hermes_profile_agents()


def hermes_sync_skills_dir(agent_id: str, *, mail_root: Path | None = None) -> Path:
    """宿主机 / 容器内 Hermes L0–L2 skills 同步目标。"""
    return _reg.hermes_sync_skills_dir(agent_id, mail_root=mail_root)


def framework_skill_id(framework: str) -> str:
    return f"framework-runtime-{framework.replace('_', '-')}"


def framework_skill_path_rel(framework: str) -> str:
    if framework not in FRAMEWORKS:
        raise ValueError(f"unknown framework: {framework}")
    v3 = ROOT / "skills" / "frameworks" / framework / "SKILL.md"
    if not v3.is_file():
        raise FileNotFoundError(f"missing v3 framework skill: {v3}")
    return f"mail/skills/frameworks/{framework}/SKILL.md"


def universal_skill_spec() -> dict:
    v3 = ROOT / "skills" / "common" / "agent-universal" / "SKILL.md"
    if not v3.is_file():
        raise FileNotFoundError(f"missing v3 skill: {v3}")
    return {
        "id": "agent-universal",
        "path": "mail/skills/common/agent-universal/SKILL.md",
        "type": "shared_skill",
        "layer": "L0",
        "always": True,
    }


def shared_protocol_spec() -> dict:
    v3 = ROOT / "skills" / "common" / "mailbus-file-protocol" / "SKILL.md"
    if not v3.is_file():
        raise FileNotFoundError(f"missing v3 skill: {v3}")
    return {
        "id": "mailbus-file-protocol",
        "path": "mail/skills/common/mailbus-file-protocol/SKILL.md",
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
    v3 = ROOT / "skills" / "roles" / "archetypes" / archetype / "SKILL.md"
    if not v3.is_file():
        raise FileNotFoundError(f"missing v3 archetype skill: {v3}")
    return {
        "id": f"role-{archetype}",
        "path": f"mail/skills/roles/archetypes/{archetype}/SKILL.md",
        "type": "role_archetype",
        "layer": "L2",
        "archetype": archetype,
        "always": True,
    }


def role_overlay_spec(agent_id: str) -> dict:
    if agent_id not in AGENT_ARCHETYPES:
        raise ValueError(f"unknown agent for overlay: {agent_id}")
    v3 = ROOT / "skills" / "roles" / "overlays" / agent_id / "SKILL.md"
    if not v3.is_file():
        raise FileNotFoundError(f"missing v3 overlay skill: {v3}")
    return {
        "id": f"role-overlay-{agent_id}",
        "path": f"mail/skills/roles/overlays/{agent_id}/SKILL.md",
        "type": "role_overlay",
        "layer": "L2",
        "agent_id": agent_id,
        "extends": AGENT_ARCHETYPES[agent_id],
        "always": True,
    }


def layer_skills_for_agent(agent_id: str, framework: str) -> list[dict]:
    """Ordered L0–L2 specs for one agent (v3 access/ + mail/skills/)."""
    return _reg.layer_skills_for_agent(agent_id, framework)


def resolve_skill_src(rel: str, *, mail_root: Path | None = None) -> Path:
    """Resolve skill path from mail/skills/ or other v3 roots."""
    return _reg.resolve_skill_src(rel, mail_root=mail_root or ROOT)


SYNCABLE_SKILL_TYPES = frozenset({
    "codex_skill",
    "framework_skill",
    "shared_skill",
    "role_archetype",
    "role_overlay",
    "skill",
})


def _prepare_skill_dest_dir(dest_dir: Path) -> None:
    """Ensure clean dest dir (Windows junction/reparse SKILL.md → rmtree)."""
    import shutil

    if dest_dir.exists() or dest_dir.is_symlink():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)


def _remove_skill_dest(path: Path) -> None:
    """Remove dest SKILL.md including broken Windows reparse points."""
    import stat

    if not path.exists() and not path.is_symlink():
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        if os.name == "nt":
            try:
                os.chmod(path, stat.S_IWRITE)
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _write_skill_copy(src: Path, dest: Path) -> None:
    """Copy skill content; read/write fallback for WinError 1920."""
    import shutil

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dest)
    except OSError:
        dest.write_bytes(src.read_bytes())


def install_skill_spec(
    spec: dict,
    skills_root: Path,
    *,
    mail_root: Path | None = None,
    use_symlink: bool = True,
) -> bool:
    """Copy or symlink one skill entry into skills_root/{id}/SKILL.md."""
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
    dest_skill = dest_dir / "SKILL.md"
    if use_symlink:
        _remove_skill_dest(dest_skill)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            rel_target = os.path.relpath(src.resolve(), dest_dir.resolve())
            dest_skill.symlink_to(rel_target)
            return True
        except OSError:
            _remove_skill_dest(dest_skill)
    _prepare_skill_dest_dir(dest_dir)
    dest_skill = dest_dir / "SKILL.md"
    try:
        _write_skill_copy(src, dest_skill)
        return True
    except OSError:
        return False


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
