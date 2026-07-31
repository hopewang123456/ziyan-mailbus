"""Application: send via MessageTransportPort (Wave3)."""
from __future__ import annotations

from typing import Any, Mapping

from lib.composition import build_transport
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.locale.errors_zh import message_zh


def send_outbound(
    data_dir: str,
    *,
    agent_id: str,
    msg_id: str,
    intent: str = "",
    body_path: str = "",
    contract_path: str = "",
    channel: str = "",
    task_id: str = "",
    step_id: str = "",
    role_type: int = 0,
    wait: bool = False,
    allow_no_spawn: bool = False,
    wait_timeout_sec: int | None = None,
    extra_headers: Mapping[str, str] | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Unified send — returns dict with ok + receipt fields + message_zh on failure.

    wait=True：file_bus 厚路径（写 inbox + Harness spawn/wait），见 W7c。
    """
    headers: dict[str, str] = {
        "data_dir": data_dir,
        "intent": intent,
        "task_id": task_id,
        "step_id": step_id,
        "role_type": str(role_type),
    }
    if channel:
        headers["channel"] = channel
    if wait:
        headers["wait"] = "1"
    if allow_no_spawn:
        headers["allow_no_spawn"] = "1"
    if wait_timeout_sec is not None:
        headers["wait_timeout_sec"] = str(int(wait_timeout_sec))
    if extra_headers:
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    msg = OutboundMessage(
        agent_id=agent_id,
        msg_id=msg_id,
        body_path=body_path,
        contract_path=contract_path,
        headers=headers,
    )
    transport = build_transport(data_dir, config)
    receipt: TransportReceipt = transport.send(msg)
    out: dict[str, Any] = {
        "ok": receipt.accepted,
        "msg_id": receipt.msg_id,
        "channel": receipt.channel,
        "detail": receipt.detail,
        "error_code": receipt.error_code,
    }
    if not receipt.accepted and receipt.error_code:
        out["message_zh"] = message_zh(receipt.error_code, receipt.detail)
    return out
