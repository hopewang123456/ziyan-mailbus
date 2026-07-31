from __future__ import annotations

from typing import Protocol, runtime_checkable

from lib.domain.types import OutboundMessage, TransportReceipt


@runtime_checkable
class MessageTransportPort(Protocol):
    def send(self, message: OutboundMessage) -> TransportReceipt: ...
