"""消息协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.message import (
    DeliveryAttemptOut,
    MessageIn,
    MessageOut,
    PublicMessageOut,
)
from mailbus.application.messaging.dto import (
    DeliveryAttemptView,
    MessageView,
    SendMessageCommand,
    make_send_command,
)


def message_command(payload: MessageIn, channel: str | None = None) -> SendMessageCommand:
    return make_send_command(
        payload.body, payload.recipient_id, payload.kind, channel or payload.channel
    )


def to_message_out(view: MessageView) -> MessageOut:
    return MessageOut(
        message_id=view.message_id,
        sender_id=view.sender_id,
        recipient_id=view.recipient_id,
        kind=view.kind,
        body=view.body,
        created_at=view.created_at,
        delivery_status=view.delivery_status,
        pair_id=view.pair_id,
    )


def to_public_message_out(view: MessageView) -> PublicMessageOut:
    return PublicMessageOut(
        message_id=view.message_id,
        kind=view.kind,
        body=view.body,
        created_at=view.created_at,
        delivery_status=view.delivery_status,
        pair_id=view.pair_id,
    )


def to_attempt_out(view: DeliveryAttemptView) -> DeliveryAttemptOut:
    return DeliveryAttemptOut(
        message_id=view.message_id,
        attempt_no=view.attempt_no,
        ok=view.ok,
        error_code=view.error_code,
        detail=view.detail,
        at=view.at,
    )
