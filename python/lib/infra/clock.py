"""Clock / PathRoot / IdGenerator default adapters (D11)."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from lib.interfaces.clock import TZ_CST


class SystemClock:
    def now_ts(self) -> float:
        return time.time()

    def now_dt(self) -> datetime:
        return datetime.now(TZ_CST)

    def now_utc_dt(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        return self.now_dt().strftime("%Y-%m-%dT%H:%M:%S%z")


class FakeClock:
    """Deterministic clock for tests; advance() moves time forward."""

    def __init__(self, start_ts: float = 1_700_000_000.0) -> None:
        self._ts = float(start_ts)

    def now_ts(self) -> float:
        return self._ts

    def advance(self, seconds: float) -> None:
        self._ts += float(seconds)

    def now_dt(self) -> datetime:
        return datetime.fromtimestamp(self._ts, tz=TZ_CST)

    def now_utc_dt(self) -> datetime:
        return datetime.fromtimestamp(self._ts, tz=timezone.utc)

    def now_iso(self) -> str:
        return self.now_dt().strftime("%Y-%m-%dT%H:%M:%S%z")


class UuidIdGenerator:
    def new_id(self, prefix: str = "") -> str:
        uid = uuid.uuid4().hex[:12]
        return f"{prefix}{uid}" if prefix else uid


class DataPathRoot:
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir

    @property
    def data_dir(self) -> str:
        return self._data_dir


def _clock():
    from lib.composition import get_context

    return get_context().clock


def now_ts() -> float:
    return _clock().now_ts()


def now_dt() -> datetime:
    return _clock().now_dt()


def now_utc_dt() -> datetime:
    return _clock().now_utc_dt()


def now_iso() -> str:
    return _clock().now_iso()
