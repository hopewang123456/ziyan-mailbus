"""HTTP A2A MessageTransportPort — async SendMessage via A2ATransport."""
from __future__ import annotations

import os

from lib.adapters.transport.codes import transport_exc_to_domain
from lib.domain.error_codes import TRANSPORT_A2A
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.transport.types import DispatchContext
from lib.utils import json_read


class HttpA2AMessageTransport:
    def __init__(self, data_dir: str = "", config: dict | None = None):
        self.data_dir = data_dir
        self.config = config

    def send(self, message: OutboundMessage) -> TransportReceipt:
        h = dict(message.headers or {})
        data_dir = h.get("data_dir") or self.data_dir
        cfg = self.config or json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else {}
        agents = cfg.get("agents") or {}
        ctx = DispatchContext(
            data_dir=data_dir,
            task_id=h.get("task_id") or "",
            step_id=h.get("step_id") or message.msg_id,
            to_agent=message.agent_id,
            role_type=int(h.get("role_type") or 0),
            intent=h.get("intent") or h.get("content") or "",
            msg_file=message.body_path or None,
        )
        try:
            from lib.transport.a2a_standard import A2ATransport

            a2a = A2ATransport(config=cfg, data_dir=data_dir)
            outcome = a2a.dispatch_async(ctx, agents)
            if outcome.get("ok"):
                return TransportReceipt(
                    msg_id=message.msg_id or outcome.get("a2a_task_id") or "",
                    accepted=True,
                    detail=str(outcome.get("a2a_task_id") or "a2a_sent"),
                    channel="http_a2a",
                )
            return TransportReceipt(
                msg_id=message.msg_id,
                accepted=False,
                detail=str(outcome.get("error") or "a2a_failed"),
                channel="http_a2a",
                error_code=TRANSPORT_A2A,
            )
        except Exception as exc:
            err = transport_exc_to_domain(exc, channel="http_a2a")
            return TransportReceipt(
                msg_id=message.msg_id,
                accepted=False,
                detail=err.message,
                channel="http_a2a",
                error_code=err.code,
            )
