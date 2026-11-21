"""消息用例：发送与收件箱投影。

收件箱不落独立表，读取时按接收人（含广播）过滤消息；
投递结果由派发器回调写入尝试表。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.messaging.dto import (
    DeliveryAttemptView,
    MessageView,
    SendMessageCommand,
)
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.messaging import rules
from mailbus.core.messaging.models import Message
from mailbus.core.messaging.ports import MessagingUnitOfWork
from mailbus.core.shared.errors import NotFoundError, PermissionDeniedError
from mailbus.core.shared.events import DeliveryResult, OutboxEvent
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class MessagingService:
    def __init__(
        self,
        uow_factory: Callable[[], MessagingUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def send(self, actor: Actor, cmd: SendMessageCommand) -> MessageView:
        ensure_allowed(
            actor.to_subject(),
            Capability.MESSAGE_SEND,
            Resource(kind="message", owner_id=actor.employee_id),
        )
        now = self._clock.now()
        message, events = rules.compose(
            self._ids.new("msg"),
            sender_id=actor.employee_id,
            recipient_id=cmd.recipient_id,
            body=cmd.body,
            kind=cmd.kind,
            channel=cmd.channel,
            pair_id=cmd.pair_id,
            now=now,
        )
        with self._uow() as uow:
            uow.messages.add(message)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return MessageView.of(message)

    def inbox(
        self, actor: Actor, limit: int = 200, offset: int = 0
    ) -> tuple[MessageView, ...]:
        with self._uow() as uow:
            messages = uow.messages.inbox(actor.employee_id, limit, offset)
        return tuple(MessageView.of(message) for message in messages)

    def list_messages(
        self,
        actor: Actor,
        *,
        agent: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        pair_id: str | None = None,
        collab_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[MessageView, ...]:
        """全局消息检索：超管看全部，普通用户只看自己收发（含广播）。"""
        viewer_id = (
            None if Capability.ALL in actor.capabilities else actor.employee_id
        )
        with self._uow() as uow:
            rows = uow.messages.search(
                viewer_id=viewer_id,
                agent=agent,
                status=status,
                since=since,
                pair_id=pair_id,
                collab_only=collab_only,
                limit=limit,
                offset=offset,
            )
        return tuple(
            MessageView.of(message, delivery_status) for message, delivery_status in rows
        )

    def list_collab(self, pair_id: str, limit: int = 50) -> tuple[MessageView, ...]:
        """公开大屏投影：只按结对读取，不校验调用者（由公开路由显式调用）。"""
        with self._uow() as uow:
            rows = uow.messages.search(pair_id=pair_id, collab_only=True, limit=limit)
        return tuple(
            MessageView.of(message, delivery_status) for message, delivery_status in rows
        )

    def get(self, actor: Actor, message_id: str) -> MessageView:
        with self._uow() as uow:
            message = uow.messages.get(message_id)
        if message is None:
            raise NotFoundError("消息不存在")
        self._ensure_can_read(actor, message)
        return MessageView.of(message)

    def attempts(
        self, actor: Actor, message_id: str
    ) -> tuple[DeliveryAttemptView, ...]:
        with self._uow() as uow:
            message = uow.messages.get(message_id)
            if message is None:
                raise NotFoundError("消息不存在")
            attempts = uow.messages.attempts(message_id)
        self._ensure_can_read(actor, message)
        return tuple(DeliveryAttemptView.of(attempt) for attempt in attempts)

    def delete(self, actor: Actor, message_id: str) -> None:
        """删除消息：仅系统配置者可操作；投递尝试一并清理。"""
        ensure_allowed(
            actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="message")
        )
        now = self._clock.now()
        with self._uow() as uow:
            message = uow.messages.get(message_id)
            if message is None:
                raise NotFoundError("消息不存在")
            uow.messages.delete(message_id)
            event = rules.deletion(message, actor_id=actor.employee_id, now=now)
            enqueue_events(uow.outbox, (event,), self._ids, now)
            uow.commit()

    @staticmethod
    def _ensure_can_read(actor: Actor, message: Message) -> None:
        if Capability.ALL in actor.capabilities:
            return
        if message.sender_id == actor.employee_id or message.recipient_id in (
            actor.employee_id,
            None,
        ):
            return
        raise PermissionDeniedError("无权查看该消息")

    def record_delivery(self, event: OutboxEvent, result: DeliveryResult) -> None:
        """派发器回调：只记录消息类事件的投递结果。"""
        if event.kind != "message.sent":
            return
        message_id = str(event.payload.get("message_id") or "")
        if not message_id:
            return
        now = self._clock.now()
        with self._uow() as uow:
            if uow.messages.get(message_id) is None:
                return
            uow.messages.add_attempt(
                message_id,
                ok=result.ok,
                error_code=result.error_code,
                detail=result.detail,
                at=now,
            )
            uow.commit()
