"""HTTP A2A transport — MessageTransportPort + A2ATransportPort."""
from __future__ import annotations

import os
from typing import Any, Mapping

from lib.adapters.transport.codes import transport_exc_to_domain
from lib.domain.error_codes import TRANSPORT_A2A
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.core.a2a.types import DispatchContext
from lib.infra.utils import json_read


class HttpA2AMessageTransport:
    """Implements MessageTransportPort.send and A2ATransportPort cancel/stream/poll."""

    def __init__(self, data_dir: str = "", config: dict | None = None):
        self.data_dir = data_dir
        self.config = config

    def _cfg(self, headers: Mapping[str, str] | None = None) -> tuple[str, dict]:
        h = dict(headers or {})
        data_dir = h.get("data_dir") or self.data_dir
        cfg = self.config or (
            json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else {}
        )
        return data_dir, cfg

    def _transport(self, data_dir: str, cfg: dict):
        from lib.core.a2a.a2a_standard import A2ATransport

        return A2ATransport(config=cfg, data_dir=data_dir)

    def send(self, message: OutboundMessage) -> TransportReceipt:
        h = dict(message.headers or {})
        data_dir, cfg = self._cfg(h)
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
            a2a = self._transport(data_dir, cfg)
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

    def cancel(
        self,
        *,
        a2a_task_id: str,
        task_id: str = "",
        step_id: str = "",
        agent_id: str = "",
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        h = dict(headers or {})
        data_dir, cfg = self._cfg(h)
        agents = cfg.get("agents") or {}
        ctx = DispatchContext(
            data_dir=data_dir,
            task_id=task_id or h.get("task_id") or "",
            step_id=step_id or h.get("step_id") or "",
            to_agent=agent_id or h.get("agent_id") or "",
            role_type=int(h.get("role_type") or 0),
        )
        try:
            return self._transport(data_dir, cfg).cancel_task(ctx, a2a_task_id, agents)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "a2a_task_id": a2a_task_id}

    def stream(self, message: OutboundMessage) -> TransportReceipt:
        # Streaming RPC not yet exposed on A2ATransport; async send is the production path.
        return self.send(message)

    def get_task(
        self,
        *,
        a2a_task_id: str,
        task_id: str = "",
        step_id: str = "",
        agent_id: str = "",
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        return self.poll_ack(
            a2a_task_id=a2a_task_id,
            task_id=task_id,
            step_id=step_id,
            agent_id=agent_id,
            headers=headers,
        )

    def poll_ack(
        self,
        *,
        a2a_task_id: str,
        task_id: str = "",
        step_id: str = "",
        agent_id: str = "",
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        h = dict(headers or {})
        data_dir, cfg = self._cfg(h)
        agents = cfg.get("agents") or {}
        ctx = DispatchContext(
            data_dir=data_dir,
            task_id=task_id or h.get("task_id") or "",
            step_id=step_id or h.get("step_id") or "",
            to_agent=agent_id or h.get("agent_id") or "",
            role_type=int(h.get("role_type") or 0),
        )
        try:
            return self._transport(data_dir, cfg).poll_task(ctx, a2a_task_id, agents=agents)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "a2a_task_id": a2a_task_id}
