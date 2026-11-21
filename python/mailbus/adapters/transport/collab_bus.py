"""协作事件总线：进程内多订阅者广播。

HTTP 路由在 FastAPI 线程池中写入，订阅方在事件循环中等待，因此发布通过
``loop.call_soon_threadsafe`` 投递；慢消费者丢弃增量，不阻塞写请求。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mailbus.adapters.system.concurrency import StreamGate
from mailbus.core.shared.errors import CapacityError

_DEFAULT_MAX_SUBSCRIBERS = 256


class InProcessEventBus:
    def __init__(
        self, gate: StreamGate | None = None, max_subscribers: int = _DEFAULT_MAX_SUBSCRIBERS
    ) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue[tuple[str, dict]]] = set()
        self._gate = gate if gate is not None else StreamGate(max_subscribers)

    @property
    def gate(self) -> StreamGate:
        return self._gate

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    @property
    def max_subscribers(self) -> int:
        return self._gate.capacity

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[tuple[str, dict]]]:
        # 兜底：路由层已按同一闸门预检，这里防止并发检查后仍超卖。
        if not self._gate.acquire():
            raise CapacityError("大屏连接数已达上限，请稍后重试")
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue(maxsize=256)
        self._queues.add(queue)
        try:
            yield queue
        finally:
            self._queues.discard(queue)
            self._gate.release()

    def publish(self, kind: str, payload: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._fanout, kind, payload)

    def _fanout(self, kind: str, payload: dict) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait((kind, payload))
            except asyncio.QueueFull:
                continue
