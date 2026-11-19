"""outbox 派发循环。

原则：
- 投递与状态变更分离：先提交取件事务释放写锁，再投递，最后另开事务记结果；
- 失败只记录尝试与退避，不改任务状态；
- 禁止在请求线程里 sleep，循环只跑在 lifespan 启动的后台任务里。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from mailbus.core.shared.ports import Transport, UnitOfWork

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        transport: Transport,
        *,
        interval_sec: float = 5.0,
        batch: int = 50,
        sweeper: Callable[[], int] | None = None,
        on_result: Callable[[OutboxEvent, DeliveryResult], None] | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._uow = uow_factory
        self._transport = transport
        self._interval = interval_sec
        self._batch = batch
        self._sweeper = sweeper
        self._on_result = on_result
        self._max_attempts = max_attempts

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except Exception:  # 单次失败不能中断派发循环
                logger.exception("派发循环单次执行失败")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue

    def tick(self) -> int:
        if self._sweeper is not None:
            self._sweeper()
        with self._uow() as uow:
            events = uow.outbox.claim_due(self._batch)
            uow.commit()
        for event in events:
            result = self._transport.send(event)
            if self._on_result is not None:
                self._on_result(event, result)
            with self._uow() as uow:
                if result.ok:
                    uow.outbox.mark_sent(event.event_id)
                elif event.attempts + 1 >= self._max_attempts:
                    uow.outbox.mark_dead(
                        event.event_id, result.error_code or "delivery_failed"
                    )
                else:
                    uow.outbox.mark_failed(event.event_id, result.error_code or "delivery_failed")
                uow.commit()
        return len(events)
