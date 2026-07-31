"""Spawn path whitelist: builtin ∪ config append (Q3B)."""
from __future__ import annotations

import os
from pathlib import Path

from lib.domain.errors import Fatal

BUILTIN_ALLOWED_BINARIES = {
    "docker", "docker.exe", "hermes", "codex", "claude", "node", "python", "python.exe",
    "opencode", "cursor", "cursor-agent", "wsl", "wsl.exe", "bash",
}


def allowed_binaries(cfg: dict | None = None) -> set[str]:
    extra = set()
    if cfg:
        for item in (cfg.get("spawn_whitelist") or cfg.get("allowed_binaries") or []):
            if item:
                extra.add(str(item))
                extra.add(Path(str(item)).name)
    return set(BUILTIN_ALLOWED_BINARIES) | extra


def assert_spawn_argv_allowed(argv: list[str], cfg: dict | None = None) -> None:
    if not argv:
        raise Fatal("empty spawn argv", code="fatal")
    binary = Path(argv[0]).name
    allowed = allowed_binaries(cfg)
    # also allow absolute paths whose basename is allowed
    if binary not in allowed and argv[0] not in allowed:
        raise Fatal(f"spawn binary not on whitelist: {argv[0]}", code="fatal")
    if os.name == "nt":
        low = binary.lower()
        if low in ("cmd.exe", "powershell.exe", "pwsh.exe"):
            raise Fatal("shell wrappers forbidden", code="fatal")
