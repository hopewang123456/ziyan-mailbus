"""Spawn path whitelist — re-export from lib.spawn_guard (legacy import path)."""
from __future__ import annotations

from lib.spawn_guard import (  # noqa: F401
    BUILTIN_ALLOWED_BINARIES,
    allowed_binaries,
    assert_spawn_argv_allowed,
)
