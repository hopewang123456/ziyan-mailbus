#!/usr/bin/env python3
"""Strip inline mailbus rules from identities; add overlay pointer."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ROOT / "identities"
WORKSPACE_IDENTITIES = [
    ROOT.parent / "lingxiao" / "IDENTITY.md",
]

OVERLAY_LINE = "> **工种 spec** → `mail/roles/overlays/{agent}/SKILL.md` · L0/L1 由 sync 注入\n"

MAILBUS_SECTION = re.compile(r"\n##\s*📬\s*mailbus[\s\S]*$", re.I)


def _agent_from_path(path: Path) -> str:
    if path.parent.name in ("identities",):
        return path.stem
    return path.parent.name if path.name == "IDENTITY.md" else path.stem


def strip_file(path: Path) -> bool:
    agent = _agent_from_path(path)
    if agent in ("README",) or ".draft" in path.name:
        return False
    text = path.read_text(encoding="utf-8")
    new = MAILBUS_SECTION.sub("", text).rstrip() + "\n"
    pointer = OVERLAY_LINE.format(agent=agent)
    if pointer.strip() not in new and agent in (
        "dali", "lingyun", "lingyan", "lingjian", "lingzhao", "xiaoqi", "yige",
        "lingjin", "lingxi", "lingtuo", "lingxun", "lingxiao", "lingzhang",
    ):
        new = new.rstrip() + "\n\n" + pointer
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def iter_identity_files() -> list[Path]:
    paths: list[Path] = []
    paths.extend(IDENTITIES.glob("*.md"))
    paths.extend(IDENTITIES.glob("*/IDENTITY.md"))
    paths.extend(p for p in WORKSPACE_IDENTITIES if p.is_file())
    return paths


def main() -> None:
    changed = 0
    for path in iter_identity_files():
        if strip_file(path):
            changed += 1
            print("stripped", path)
    print(f"done: {changed} files")


if __name__ == "__main__":
    main()
