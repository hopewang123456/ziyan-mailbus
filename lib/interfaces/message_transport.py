"""Message / A2A / bridged-agent transport ports (Wave 2)."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from lib.domain.types import OutboundMessage, TransportReceipt


@runtime_checkable
class MessageTransportPort(Protocol):
    """Narrow outbound send port (file_bus / http_a2a / webhook)."""

    def send(self, message: OutboundMessage) -> TransportReceipt: ...


@runtime_checkable
class A2ATransportPort(Protocol):
    """A2A-capable transport: send / cancel / stream / get_task (poll).

    Matches real usage in ``lib.core.a2a`` (A2ATransport) and
    ``lib.adapters.transport.http_a2a`` (MessageTransportPort send wrapper).
    """

    def send(self, message: OutboundMessage) -> TransportReceipt: ...

    def cancel(
        self,
        *,
        a2a_task_id: str,
        task_id: str = "",
        step_id: str = "",
        agent_id: str = "",
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def stream(self, message: OutboundMessage) -> TransportReceipt: ...

    def get_task(
        self,
        *,
        a2a_task_id: str,
        task_id: str = "",
        step_id: str = "",
        agent_id: str = "",
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def poll_ack(
        self,
        *,
        a2a_task_id: str,
        task_id: str = "",
        step_id: str = "",
        agent_id: str = "",
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class BridgedAgentPort(Protocol):
    """Non-A2A agent bridge (CLI spawn + file-bus ack / result)."""

    def send(self, message: OutboundMessage) -> TransportReceipt: ...

    def cancel(
        self,
        *,
        agent_id: str,
        msg_id: str = "",
        task_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]: ...

    def status(
        self,
        *,
        agent_id: str,
        msg_id: str = "",
        task_id: str = "",
    ) -> dict[str, Any]: ...
