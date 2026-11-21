"""进程内并发闸门：长连接等稀缺资源的计数与上限。"""

from __future__ import annotations

import threading


class StreamGate:
    """线程安全的计数闸门；路由预检与生成器释放共用同一实例。"""

    def __init__(self, capacity: int) -> None:
        self._capacity = max(0, capacity)
        self._lock = threading.Lock()
        self._active = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    @property
    def full(self) -> bool:
        with self._lock:
            return self._active >= self._capacity

    def acquire(self) -> bool:
        with self._lock:
            if self._active >= self._capacity:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self._active > 0:
                self._active -= 1
