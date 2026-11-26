"""消息发送的纯函数规则。"""

from __future__ import annotations

from datetime import datetime

from mailbus.core.messaging.models import Message
from mailbus.core.shared.errors import InvalidStateError
from mailbus.core.shared.events import DomainEvent

_MAX_BODY = 4000
_MAX_KIND = 32


def compose(
    message_id: str,
    *,
    sender_id: str,
    recipient_id: str | None,
    body: str,
    kind: str = "note",
    channel: str = "file_bus",
    pair_id: str | None = None,
    now: datetime,
) -> tuple[Message, tuple[DomainEvent, ...]]:
    text = body.strip()
    if not text:
        raise InvalidStateError("消息内容不能为空")
    if len(text) > _MAX_BODY:
        raise InvalidStateError(f"消息内容不能超过 {_MAX_BODY} 个字符")
    label = (kind or "note").strip()
    if not label or len(label) > _MAX_KIND:
        raise InvalidStateError("消息类型不合法")
    message = Message(
        message_id=message_id,
        sender_id=sender_id,
        recipient_id=recipient_id or None,
        body=text,
        kind=label,
        created_at=now,
        channel=channel,
        pair_id=pair_id or None,
    )
    event = DomainEvent(
        kind="message.sent",
        payload={
            "message_id": message_id,
            "sender_id": sender_id,
            "recipient_id": message.recipient_id,
            "channel": channel,
            "pair_id": message.pair_id,
            "body": message.body,
            "kind": label,
            "at": now.isoformat(),
        },
    )
    return message, (event,)


def deletion(message: Message, *, actor_id: str, now: datetime) -> DomainEvent:
    """消息删除事件：仅超管删除，保留审计轨迹。"""
    return DomainEvent(
        kind="message.deleted",
        payload={
            "message_id": message.message_id,
            "actor_id": actor_id,
            "at": now.isoformat(),
        },
    )
