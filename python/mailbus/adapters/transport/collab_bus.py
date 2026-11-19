"""协作事件总线：进程内多订阅者广播。

HTTP 路由在 FastAPI 线程池中写入，订阅方在事件循环中等待，因此发布通过
``loop.call_soon_threadsafe`` 投递；慢消费者丢弃增量，不阻塞写请求。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class InProcessEventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue[tuple[str, dict]]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[tuple[str, dict]]]:
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue(maxsize=256)
        self._queues.add(queue)
        try:
            yield queue
        finally:
            self._queues.discard(queue)

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
