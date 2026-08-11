"""MessageTransportPort adapters (Wave3 · S2)."""
from __future__ import annotations

from lib.adapters.transport.file_bus import FileBusMessageTransport
from lib.adapters.transport.http_a2a import HttpA2AMessageTransport
from lib.adapters.transport.router import SelectingMessageTransport, build_message_transport, resolve_channel
from lib.adapters.transport.webhook import WebhookMessageTransport

__all__ = [
    "FileBusMessageTransport",
    "HttpA2AMessageTransport",
    "SelectingMessageTransport",
    "WebhookMessageTransport",
    "build_message_transport",
    "resolve_channel",
]
