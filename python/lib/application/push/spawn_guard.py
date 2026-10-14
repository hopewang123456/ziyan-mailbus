"""Spawn path whitelist — backwards-compat re-export (SoT: lib/domain/spawn_guard.py)."""
from __future__ import annotations

from lib.domain.spawn_guard import (  # noqa: F401
    BUILTIN_ALLOWED_BINARIES,
    allowed_binaries,
    assert_spawn_argv_allowed,
)
