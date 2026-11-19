"""系统时钟。领域层只依赖 Clock 协议，测试可替换为假时钟。"""

from __future__ import annotations

from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
