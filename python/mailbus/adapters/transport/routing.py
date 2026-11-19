"""按事件上的 channel 选择出站通道；未知通道直接失败以触发重试/死信。"""

from __future__ import annotations

from collections.abc import Mapping

from mailbus.core.shared.events import DeliveryResult, OutboxEvent
from mailbus.core.shared.ports import Transport


class RoutingTransport:
    def __init__(self, channels: Mapping[str, Transport], default: str = "file_bus") -> None:
        self._channels = dict(channels)
        self._default = default

    def send(self, event: OutboxEvent) -> DeliveryResult:
        channel = str(event.payload.get("channel") or self._default)
        transport = self._channels.get(channel)
        if transport is None:
            return DeliveryResult(ok=False, error_code="unknown_channel", detail=channel)
        return transport.send(event)
