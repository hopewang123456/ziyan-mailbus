"""Mailbus unified lifecycle rules for bridged (non-A2A) agents."""
from __future__ import annotations

from enum import Enum


DEFAULT_TIMEOUT_SEC = 300
DEFAULT_RETRY_LIMIT = 2


class ExitClass(str, Enum):
    OK = "ok"
    RETRYABLE = "retryable"
    FATAL = "fatal"
    NEEDS_HUMAN = "needs_human"
    TIMEOUT = "timeout"


# Process exit code → Mailbus classification (unified rules).
EXIT_CODE_MAP: dict[int, ExitClass] = {
    0: ExitClass.OK,
    1: ExitClass.RETRYABLE,
    2: ExitClass.FATAL,
    75: ExitClass.RETRYABLE,  # EX_TEMPFAIL
    124: ExitClass.TIMEOUT,  # common timeout wrapper
    137: ExitClass.FATAL,  # SIGKILL
    143: ExitClass.FATAL,  # SIGTERM
}


def classify_exit(code: int | None, *, timed_out: bool = False) -> ExitClass:
    if timed_out:
        return ExitClass.TIMEOUT
    if code is None:
        return ExitClass.RETRYABLE
    return EXIT_CODE_MAP.get(int(code), ExitClass.RETRYABLE if int(code) > 0 else ExitClass.OK)


def should_retry(
    exit_class: ExitClass,
    *,
    attempt: int,
    retry_limit: int = DEFAULT_RETRY_LIMIT,
) -> bool:
    if attempt >= retry_limit:
        return False
    return exit_class in (ExitClass.RETRYABLE, ExitClass.TIMEOUT)


def timeout_seconds(agent_cfg: dict | None = None, default: int = DEFAULT_TIMEOUT_SEC) -> int:
    cfg = agent_cfg or {}
    for key in ("bridge_timeout_sec", "cli_timeout_sec", "ack_timeout", "timeout"):
        raw = cfg.get(key)
        if raw is not None:
            try:
                return max(1, int(raw))
            except (TypeError, ValueError):
                continue
    return default
