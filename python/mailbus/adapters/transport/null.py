"""空传输：B0 只验证 outbox 流程闭环，不做真实投递。"""

from __future__ import annotations

import logging

from mailbus.core.shared.events import DeliveryResult, OutboxEvent

logger = logging.getLogger(__name__)


class NullTransport:
    def send(self, event: OutboxEvent) -> DeliveryResult:
        logger.debug("丢弃事件 %s（%s）：B0 空传输", event.event_id, event.kind)
        return DeliveryResult(ok=True)
