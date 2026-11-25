"""消息用例的输入/输出模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.messaging.models import DeliveryAttempt, Message


@dataclass(frozen=True, slots=True)
class SendMessageCommand:
    body: str
    recipient_id: str | None = None
    kind: str = "note"
    channel: str = "file_bus"
    pair_id: str | None = None


@dataclass(frozen=True, slots=True)
class MessageView:
    message_id: str
    sender_id: str
    recipient_id: str | None
    kind: str
    body: str
    created_at: datetime | None
    delivery_status: str | None = None
    pair_id: str | None = None
    channel: str = "file_bus"

    @classmethod
    def of(cls, message: Message, delivery_status: str | None = None) -> "MessageView":
        return cls(
            message_id=message.message_id,
            sender_id=message.sender_id,
            recipient_id=message.recipient_id,
            kind=message.kind,
            body=message.body,
            created_at=message.created_at,
            delivery_status=delivery_status,
            pair_id=message.pair_id,
            channel=message.channel,
        )


@dataclass(frozen=True, slots=True)
class DeliveryAttemptView:
    message_id: str
    attempt_no: int
    ok: bool
    error_code: str | None
    detail: str | None
    at: datetime | None

    @classmethod
    def of(cls, attempt: DeliveryAttempt) -> "DeliveryAttemptView":
        return cls(
            message_id=attempt.message_id,
            attempt_no=attempt.attempt_no,
            ok=attempt.ok,
            error_code=attempt.error_code,
            detail=attempt.detail,
            at=attempt.at,
        )


def make_send_command(
    body: str,
    recipient_id: str | None = None,
    kind: str = "note",
    channel: str = "file_bus",
    pair_id: str | None = None,
) -> SendMessageCommand:
    return SendMessageCommand(
        body=body,
        recipient_id=recipient_id,
        kind=kind,
        channel=channel,
        pair_id=pair_id,
    )
