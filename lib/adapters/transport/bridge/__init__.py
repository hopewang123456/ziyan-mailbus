"""CLI / file-bus bridge for non-A2A agents (Wave 2)."""
from __future__ import annotations

from lib.adapters.transport.bridge.cli_bridge import CliBridgedAgent
from lib.adapters.transport.bridge.lifecycle_rules import (
    DEFAULT_RETRY_LIMIT,
    DEFAULT_TIMEOUT_SEC,
    ExitClass,
    classify_exit,
    should_retry,
)

__all__ = [
    "CliBridgedAgent",
    "DEFAULT_RETRY_LIMIT",
    "DEFAULT_TIMEOUT_SEC",
    "ExitClass",
    "classify_exit",
    "should_retry",
]
