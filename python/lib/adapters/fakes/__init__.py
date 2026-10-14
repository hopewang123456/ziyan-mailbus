"""In-memory / deterministic fakes for port tests (no real CLI)."""
from __future__ import annotations

from lib.adapters.fakes.bridged import FakeBridgedAgent
from lib.adapters.fakes.integrations import FakeIntegrations
from lib.adapters.fakes.ops import FakeOps
from lib.adapters.fakes.result_store import FakeResultStore
from lib.adapters.fakes.runtime import FakeRuntime
from lib.adapters.fakes.transport import FakeA2ATransport, FakeMessageTransport
from lib.infra.clock import FakeClock

__all__ = [
    "FakeA2ATransport",
    "FakeBridgedAgent",
    "FakeClock",
    "FakeIntegrations",
    "FakeMessageTransport",
    "FakeOps",
    "FakeResultStore",
    "FakeRuntime",
]
