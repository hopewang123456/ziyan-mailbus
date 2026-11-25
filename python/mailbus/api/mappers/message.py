"""消息协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.contract.message import (
    MessageListOut,
    MessageOut as ContractMessageOut,
    MessageTraceEventOut,
    MessageTraceOut,
)
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


def to_contract_message_out(view: MessageView) -> ContractMessageOut:
    return ContractMessageOut(
        message_id=view.message_id,
        sender_id=view.sender_id,
        recipient_id=view.recipient_id,
        kind=view.kind,
        body=view.body,
        channel=view.channel,
        pair_id=view.pair_id,
        delivery_status=view.delivery_status,
        created_at=view.created_at,
    )


def to_message_list_out(
    views: tuple[MessageView, ...], total: int, limit: int, offset: int
) -> MessageListOut:
    return MessageListOut(
        items=[to_contract_message_out(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
    )


def to_trace_out(
    view: MessageView, attempts: tuple[DeliveryAttemptView, ...]
) -> MessageTraceOut:
    events = [
        MessageTraceEventOut(
            at=view.created_at,
            status="sent",
            channel=view.channel,
            detail={},
        )
    ]
    events.extend(
        MessageTraceEventOut(
            at=attempt.at,
            status="delivered" if attempt.ok else "failed",
            attempt_no=attempt.attempt_no,
            channel=view.channel,
            error_code=attempt.error_code,
            detail={"detail": attempt.detail} if attempt.detail else {},
        )
        for attempt in attempts
    )
    return MessageTraceOut(message_id=view.message_id, events=events)
