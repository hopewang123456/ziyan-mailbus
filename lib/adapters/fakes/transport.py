"""Fake A2A / message transport — records calls, no network."""
from __future__ import annotations

from typing import Any, Mapping

from lib.domain.types import OutboundMessage, TransportReceipt


class FakeA2ATransport:
    """Implements A2ATransportPort for tests / dry-run."""

    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.sent: list[OutboundMessage] = []
        self.cancels: list[dict[str, Any]] = []
        self.polls: list[dict[str, Any]] = []
        self.streams: list[OutboundMessage] = []

    def send(self, message: OutboundMessage) -> TransportReceipt:
        self.sent.append(message)
        return TransportReceipt(
            msg_id=message.msg_id,
            accepted=self.accept,
            detail="fake",
            channel="fake_a2a",
            error_code="" if self.accept else "transport_a2a",
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
        rec = {
            "a2a_task_id": a2a_task_id,
            "task_id": task_id,
            "step_id": step_id,
            "agent_id": agent_id,
            "headers": dict(headers or {}),
        }
        self.cancels.append(rec)
        return {"ok": True, **rec}

    def stream(self, message: OutboundMessage) -> TransportReceipt:
        self.streams.append(message)
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
        rec = {
            "a2a_task_id": a2a_task_id,
            "task_id": task_id,
            "step_id": step_id,
            "agent_id": agent_id,
            "headers": dict(headers or {}),
        }
        self.polls.append(rec)
        return {"ok": True, "state": "completed", **rec}


class FakeMessageTransport:
    """Implements MessageTransportPort for tests / dry-run."""

    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.sent: list[OutboundMessage] = []

    def send(self, message: OutboundMessage) -> TransportReceipt:
        self.sent.append(message)
        return TransportReceipt(
            msg_id=message.msg_id,
            accepted=self.accept,
            detail="fake",
            channel="fake",
            error_code="" if self.accept else "delivery_failed",
        )
