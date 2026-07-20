"""Framework runtime skill paths — shared by patch + sync scripts."""
from __future__ import annotations

from pathlib import Path

from .constants import MAILBUS_ROOT, MAILBUS_SKILLS_ROOT

ROOT = MAILBUS_ROOT
SKILLS = MAILBUS_SKILLS_ROOT

FRAMEWORK_SKILL_DIRS: dict[str, str] = {
    "hermes": "frameworks/hermes/SKILL.md",
    "hermes_profile": "frameworks/hermes_profile/SKILL.md",
    "opencode": "frameworks/opencode/SKILL.md",
    "codex": "frameworks/codex/SKILL.md",
    "claude_code": "frameworks/claude_code/SKILL.md",
    "openclaw": "frameworks/openclaw/SKILL.md",
    "cline": "frameworks/cline/SKILL.md",
    "cursor": "frameworks/cursor/SKILL.md",
}

SHARED_PROTOCOL = "common/mailbus-file-protocol/SKILL.md"


def framework_skill_id(framework: str) -> str:
    return f"framework-runtime-{framework.replace('_', '-')}"


def framework_skill_path_rel(framework: str) -> str:
    rel = FRAMEWORK_SKILL_DIRS.get(framework)
    if not rel:
        raise ValueError(f"unknown framework: {framework}")
    return f"mail/skills/{rel}"


def shared_protocol_spec() -> dict:
    return {
        "id": "mailbus-file-protocol",
        "path": f"mail/skills/{SHARED_PROTOCOL}",
        "type": "shared_skill",
        "always": True,
    }


def framework_skill_spec(framework: str) -> dict:
    return {
        "id": framework_skill_id(framework),
        "path": framework_skill_path_rel(framework),
        "type": "framework_skill",
        "framework": framework,
        "always": True,
    }


def resolve_skill_src(rel: str, *, mail_root: Path | None = None) -> Path:
    """Resolve mail/skills/... or legacy mail/adapters/ paths from repo root."""
    mail_root = mail_root or ROOT
    skills = MAILBUS_SKILLS_ROOT if mail_root == ROOT else (mail_root / "skills")
    ai_tools = mail_root.parent
    rel = (rel or "").replace("\\", "/")
    if rel.startswith("mailbus-core/skills/"):
        return skills / rel[len("mailbus-core/skills/"):]
    if rel.startswith("mail/skills/"):
        return skills / rel[len("mail/skills/"):]
    if rel.startswith("mail/adapters/"):
        tail = rel[len("mail/adapters/"):]
        if tail.startswith("_shared/mailbus-file-protocol"):
            return skills / "common" / "mailbus-file-protocol" / "SKILL.md"
        if "/framework-runtime/" in tail:
            fw, _ = tail.split("/framework-runtime/", 1)
            return skills / "frameworks" / fw / "SKILL.md"
    if rel.startswith(".codex/"):
        return ai_tools / rel
    if rel.startswith("store/"):
        return mail_root / rel
    p = Path(rel)
    return p if p.is_absolute() else ai_tools / rel


SYNCABLE_SKILL_TYPES = frozenset({"codex_skill", "framework_skill", "shared_skill"})


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
            dest_skill.symlink_to(src.resolve())
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
