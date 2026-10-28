"""Fake BridgedAgentPort — records calls, no CLI spawn."""
from __future__ import annotations

from typing import Any

from lib.domain.types import OutboundMessage, TransportReceipt


class FakeBridgedAgent:
    """Implements BridgedAgentPort for tests / dry-run."""

    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.sent: list[OutboundMessage] = []
        self.cancels: list[dict[str, Any]] = []
        self.statuses: list[dict[str, Any]] = []

    def send(self, message: OutboundMessage) -> TransportReceipt:
        self.sent.append(message)
        return TransportReceipt(
            msg_id=message.msg_id,
            accepted=self.accept,
            detail="fake_bridge",
            channel="fake_bridge",
            error_code="" if self.accept else "transport_file_bus",
        )

    def cancel(
        self,
        *,
        agent_id: str,
        msg_id: str = "",
        task_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        rec = {
            "ok": True,
            "agent_id": agent_id,
            "msg_id": msg_id,
            "task_id": task_id,
            "reason": reason or "cancelled",
        }
        self.cancels.append(rec)
        return rec

    def status(
        self,
        *,
        agent_id: str,
        msg_id: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        rec = {
            "agent_id": agent_id,
            "msg_id": msg_id,
            "task_id": task_id,
            "running": False,
            "acked": True,
            "exit_class": "ok",
        }
        self.statuses.append(rec)
        return rec


# ── L3 装配登记（composition.assemble("bridged_agent", ...) 查表用）──────


def _build_fake_bridged_agent(ctx: dict) -> "FakeBridgedAgent":
    return FakeBridgedAgent()


from lib.interfaces.assembler import register  # noqa: E402  (登记置于类定义后)

register("bridged_agent", "fake")(_build_fake_bridged_agent)
