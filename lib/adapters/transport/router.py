"""Selecting MessageTransportPort — file_bus | http_a2a | webhook."""
from __future__ import annotations

import os
from typing import Mapping

from lib.adapters.transport.file_bus import FileBusMessageTransport
from lib.adapters.transport.http_a2a import HttpA2AMessageTransport
from lib.adapters.transport.webhook import WebhookMessageTransport
from lib.domain.error_codes import TRANSPORT_CHANNEL_UNKNOWN
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.interfaces.message_transport import MessageTransportPort
from lib.infra.utils import json_read

CHANNELS = ("file_bus", "http_a2a", "webhook", "a2a_standard")


def resolve_channel(agent_id: str, headers: Mapping[str, str], cfg: dict) -> str:
    forced = (headers.get("channel") or headers.get("force_transport") or "").strip()
    if forced in ("a2a_standard", "http_a2a", "a2a"):
        return "http_a2a"
    if forced in CHANNELS:
        return "webhook" if forced == "webhook" else forced
    agents = cfg.get("agents") or {}
    ac = agents.get(agent_id) or {}
    if ac.get("webhook_url"):
        # prefer explicit webhook when configured and no a2a card
        ch = ((ac.get("channels") or {}).get("preferred") or "").strip()
        if ch == "webhook":
            return "webhook"
    channels = ac.get("channels") or {}
    if channels.get("a2a") or ac.get("a2a_endpoint") or ac.get("agent_card_url"):
        return "http_a2a"
    if ac.get("webhook_url"):
        return "webhook"
    return "file_bus"


class SelectingMessageTransport:
    def __init__(self, data_dir: str, config: dict | None = None):
        self.data_dir = data_dir
        self.config = config or json_read(os.path.join(data_dir, "config.json"), {})
        self._file = FileBusMessageTransport()
        self._a2a = HttpA2AMessageTransport(data_dir, self.config)
        self._webhook = WebhookMessageTransport(data_dir, self.config)

    def send(self, message: OutboundMessage) -> TransportReceipt:
        h = dict(message.headers or {})
        if "data_dir" not in h:
            h = {**h, "data_dir": self.data_dir}
            message = OutboundMessage(
                agent_id=message.agent_id,
                msg_id=message.msg_id,
                body_path=message.body_path,
                contract_path=message.contract_path,
                headers=h,
            )
        channel = resolve_channel(message.agent_id, h, self.config)
        if channel == "http_a2a":
            receipt = self._a2a.send(message)
            if receipt.accepted:
                return receipt
            # fallback file_bus (S2 alignment with router policy)
            fb = self._file.send(message)
            return TransportReceipt(
                msg_id=fb.msg_id or message.msg_id,
                accepted=fb.accepted,
                detail=f"a2a_fail:{receipt.detail};fallback:{fb.detail}",
                channel="file_bus" if fb.accepted else "http_a2a",
                error_code="" if fb.accepted else (receipt.error_code or fb.error_code),
            )
        if channel == "webhook":
            return self._webhook.send(message)
        if channel == "file_bus":
            return self._file.send(message)
        return TransportReceipt(
            msg_id=message.msg_id,
            accepted=False,
            detail=f"unknown channel {channel}",
            channel=channel,
            error_code=TRANSPORT_CHANNEL_UNKNOWN,
        )


def build_message_transport(data_dir: str, config: dict | None = None) -> MessageTransportPort:
    return SelectingMessageTransport(data_dir, config)
