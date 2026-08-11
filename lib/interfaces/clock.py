from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

TZ_CST = timezone(timedelta(hours=8))


@runtime_checkable
class Clock(Protocol):
    def now_ts(self) -> float: ...

    def now_dt(self) -> datetime:
        """Local wall clock used by mailbus ISO stamps (+08:00)."""
        ...

    def now_utc_dt(self) -> datetime: ...

    def now_iso(self) -> str: ...


@runtime_checkable
class IdGenerator(Protocol):
    def new_id(self, prefix: str = "") -> str: ...


@runtime_checkable
class PathRoot(Protocol):
    @property
    def data_dir(self) -> str: ...
