"""进程内滑动窗口限流：按 key 限制单位时间内的调用次数。"""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """轻量限流器；键通常取客户端 IP，用于保护匿名写接口。"""

    def __init__(self, max_events: int, window_sec: float) -> None:
        self._max = max(1, max_events)
        self._window = max(0.1, window_sec)
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        stamp = time.monotonic() if now is None else now
        cutoff = stamp - self._window
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self._max:
                return False
            hits.append(stamp)
            if len(self._hits) > 4096:
                self._prune(cutoff)
            return True

    def _prune(self, cutoff: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            self._hits.pop(key, None)
