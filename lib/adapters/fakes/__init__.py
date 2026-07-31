"""In-memory / deterministic fakes for port tests (no real CLI)."""
from __future__ import annotations

from lib.adapters.clock import FakeClock
from lib.adapters.fakes.result_store import FakeResultStore
from lib.adapters.fakes.runtime import FakeRuntime

__all__ = [
    "FakeClock",
    "FakeResultStore",
    "FakeRuntime",
]
