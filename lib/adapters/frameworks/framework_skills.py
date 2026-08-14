"""Framework runtime skill paths — shared by patch + sync scripts."""
from __future__ import annotations

import platform
from pathlib import Path

from lib.infra.constants import MAILBUS_ROOT, MAILBUS_SKILLS_ROOT

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
    """Resolve mail/skills/..., mailbus-core/skills/..., or Obsidian Vault rel paths.

    委托 agent_registry 统一解析（含 Vault 相对路径与 .md 回退），
    再兜底处理 mail/adapters/ 与 store/ 旧形态。
    """
    from lib.adapters.config.agent_registry import resolve_skill_src as _resolve_vault

    mail_root = mail_root or ROOT
    skills = MAILBUS_SKILLS_ROOT if mail_root == ROOT else (mail_root / "skills")
    ai_tools = mail_root.parent
    rel = (rel or "").replace("\\", "/")
    if rel.startswith("mail/adapters/"):
        tail = rel[len("mail/adapters/"):]
        if tail.startswith("_shared/mailbus-file-protocol"):
            return skills / "common" / "mailbus-file-protocol" / "SKILL.md"
        if "/framework-runtime/" in tail:
            fw, _ = tail.split("/framework-runtime/", 1)
            return skills / "frameworks" / fw / "SKILL.md"
    if rel.startswith("store/"):
        return mail_root / rel
    return _resolve_vault(rel, mail_root=mail_root)


SYNCABLE_SKILL_TYPES = frozenset({
    "codex_skill",
    "framework_skill",
    "shared_skill",
    "role_archetype",
    "role_overlay",
})


def _install_file_link(dest_file: Path, src_file: Path) -> None:
    """Link dest_file → src_file as a single-file hardlink (Windows) / symlink (POSIX)."""
    from lib.adapters.config.sync_layers import _is_reparse_or_symlink

    if dest_file.exists() or dest_file.is_symlink():
        if _is_reparse_or_symlink(dest_file) or dest_file.exists():
            if platform.system() == "Windows":
                import subprocess

                subprocess.run(["cmd", "/c", "del", str(dest_file)], check=False, capture_output=True)
            else:
                dest_file.unlink()
        else:
            raise RuntimeError(f"Refusing to replace real file: {dest_file}")
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    _link_file(dest_file, src_file)


def _link_file(dest: Path, src: Path) -> None:
    """Create a file-level hardlink (Windows) or symlink (POSIX)."""
    if platform.system() == "Windows":
        import subprocess

        subprocess.run(
            ["cmd", "/c", "mklink", "/H", str(dest), str(src)],
            check=True,
            capture_output=True,
        )
    else:
        dest.symlink_to(src)


def _install_dir_link(dest_dir: Path, src_dir: Path) -> None:
    """Link dest_dir → src_dir as a directory (junction on Windows, symlink on POSIX)."""
    from lib.adapters.config.sync_layers import _link_dir, _is_reparse_or_symlink

    if dest_dir.exists() or dest_dir.is_symlink():
        if _is_reparse_or_symlink(dest_dir):
            if platform.system() == "Windows":
                import subprocess

                subprocess.run(["cmd", "/c", "rmdir", str(dest_dir)], check=False, capture_output=True)
            else:
                dest_dir.unlink()
        else:
            raise RuntimeError(f"Refusing to replace real directory: {dest_dir}")
    _link_dir(dest_dir, src_dir)


def install_skill_spec(
    spec: dict,
    skills_root: Path,
    *,
    mail_root: Path | None = None,
    use_symlink: bool = True,
) -> bool:
    """Install one skill entry as a link (junction/symlink).

    - 目录型技能（`…/SKILL.md`）：整目录链接，references/scripts 附件保持同步。
    - 单文件技能（role_overlay `overlay-<name>.md`）：文件级硬链接/symlink。
    """
    import shutil

    stype = spec.get("type") or ""
    if stype not in SYNCABLE_SKILL_TYPES:
        return False
    rel = spec.get("path") or ""
    sid = spec.get("id") or Path(rel).stem
    src = resolve_skill_src(rel, mail_root=mail_root)
    if not src.is_file():
        return False
    if src.name == "SKILL.md" and src.parent != src:
        # 目录型：链接 src 所在目录，references/scripts 附件同步
        dest_dir = skills_root / sid
        if use_symlink:
            _install_dir_link(dest_dir, src.parent)
            return True
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_skill = dest_dir / "SKILL.md"
        shutil.copy2(src, dest_skill)
        return True
    # 单文件型（role_overlay 等）：链接文件本体
    dest_dir = skills_root / sid
    dest_file = dest_dir / src.name
    if use_symlink:
        _install_file_link(dest_file, src)
        return True
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_file)
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
