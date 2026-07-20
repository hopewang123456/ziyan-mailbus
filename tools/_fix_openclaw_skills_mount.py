# -*- coding: utf-8 -*-
"""Fix OpenClaw skills SoT for Docker + merge leftover skills into Vault."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

VAULT_OC = Path(r"E:/Obsidian/Vaults/Agent/skills/library/openclaw")
SPACE = Path(r"E:/ai_tools/openclaw_space")
SPACE_SKILLS = SPACE / "skills"
MATT = SPACE / "matt-skills" / "skills"
OLD_QCLAW = Path(r"E:/Obsidian/Vaults/Agent/skills/02-agent-specific/openclaw-qclaw")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=False)


def is_reparse(p: Path) -> bool:
    import ctypes

    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
    return attrs != -1 and bool(attrs & 0x400)


def merge_skill_tree(src_root: Path, dest_root: Path) -> int:
    """Copy skill packages (dirs containing SKILL.md) into dest if missing."""
    if not src_root.is_dir():
        return 0
    n = 0
    for skill_md in src_root.rglob("SKILL.md"):
        pkg = skill_md.parent
        # relative package name under src_root
        try:
            rel = pkg.relative_to(src_root)
        except ValueError:
            continue
        dest = dest_root / rel
        if dest.exists() and (dest / "SKILL.md").exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(pkg, dest)
        print(f"  merged {rel}")
        n += 1
    return n


def main() -> None:
    VAULT_OC.mkdir(parents=True, exist_ok=True)

    print("=== 1. Merge matt-skills -> Vault library/openclaw ===")
    print("merged matt:", merge_skill_tree(MATT, VAULT_OC))

    print("=== 2. Merge leftover 02-agent-specific/openclaw-qclaw ===")
    print("merged old:", merge_skill_tree(OLD_QCLAW, VAULT_OC))

    print("=== 3. Replace openclaw_space/skills junction with real dir ===")
    # Docker nested bind over a Windows junction is unreliable.
    # Keep SoT in Vault; compose binds Vault -> /workspace/skills.
    # Host ~/.qclaw/skills remains a junction (native client).
    if SPACE_SKILLS.exists() or SPACE_SKILLS.is_symlink() or is_reparse(SPACE_SKILLS):
        if is_reparse(SPACE_SKILLS) or SPACE_SKILLS.is_symlink():
            run(["cmd", "/c", "rmdir", str(SPACE_SKILLS)])
        else:
            bak = SPACE / "skills.__pre-docker-fix"
            if bak.exists():
                shutil.rmtree(bak, ignore_errors=True)
            SPACE_SKILLS.rename(bak)
            print("  renamed real skills ->", bak)
    SPACE_SKILLS.mkdir(parents=True, exist_ok=True)
    readme = SPACE_SKILLS / "README-VAULT-SOT.md"
    readme.write_text(
        "# OpenClaw skills SoT\n\n"
        "真源在 Obsidian：`Agent/skills/library/openclaw/`。\n\n"
        "- Docker：compose 将 Vault 挂到 `/workspace/skills`\n"
        "- 本机 QClaw：`%USERPROFILE%\\.qclaw\\skills` → Vault junction\n"
        "- 本目录仅为占位，避免 junction 破坏 Docker 嵌套挂载\n",
        encoding="utf-8",
    )
    print("  placeholder skills dir ready, reparse=", is_reparse(SPACE_SKILLS))

    print("=== 4. Recreate openclaw container mounts ===")
    run(
        [
            "wsl",
            "-e",
            "bash",
            "-lc",
            "cd /mnt/e/ai_tools/mail/docker-agents && "
            "docker compose -p docker-agents up -d --force-recreate openclaw",
        ]
    )

    print("=== 5. Verify in container ===")
    run(
        [
            "wsl",
            "-e",
            "bash",
            "-lc",
            "sleep 3; docker exec docker-agents-openclaw-1 sh -c '"
            "echo mounts=; grep skills /proc/self/mountinfo | head -5; "
            "echo count=$(find /workspace/skills -name SKILL.md 2>/dev/null | wc -l); "
            "ls -la /workspace/skills | head -8'",
        ]
    )

    print("Vault SKILL.md now:", sum(1 for _ in VAULT_OC.rglob("SKILL.md")))


if __name__ == "__main__":
    main()
