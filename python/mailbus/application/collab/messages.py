"""协同消息用例：在结对范围内发送与检索消息。

消息本体仍写入 ``msg_messages``，这里只补 pair 维度的准入校验。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.identity.dto import Actor
from mailbus.application.messaging.dto import MessageView, SendMessageCommand
from mailbus.application.messaging.service import MessagingService
from mailbus.core.collab.models import Pair
from mailbus.core.collab.ports import CollabEventBus, CollabUnitOfWork
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
)
from mailbus.core.shared.values import Capability


class CollabMessageService:
    def __init__(
        self,
        messaging: MessagingService,
        uow_factory: Callable[[], CollabUnitOfWork],
        events: CollabEventBus,
    ) -> None:
        self._messaging = messaging
        self._uow = uow_factory
        self._events = events

    def send(
        self,
        actor: Actor,
        *,
        pair_id: str,
        body: str,
        recipient_id: str | None = None,
        kind: str = "note",
        channel: str = "file_bus",
    ) -> MessageView:
        pair = self._load(actor, pair_id)
        if pair.state != "active":
            raise InvalidStateError("结对已结束，不能继续发送协同消息")
        view = self._messaging.send(
            actor,
            SendMessageCommand(
                body=body,
                recipient_id=recipient_id,
                kind=kind,
                channel=channel,
                pair_id=pair_id,
            ),
        )
        # 公开大屏事件：只带脱敏字段，不暴露发送者/接收者身份。
        self._events.publish(
            "message.created",
            {
                "message_id": view.message_id,
                "pair_id": view.pair_id,
                "kind": view.kind,
                "body": view.body,
                "created_at": view.created_at.isoformat() if view.created_at else None,
            },
        )
        return view

    def list_messages(
        self,
        actor: Actor,
        *,
        pair_id: str | None = None,
        limit: int = 100,
    ) -> tuple[MessageView, ...]:
        if pair_id is not None:
            self._load(actor, pair_id)
        return self._messaging.list_messages(
            actor, pair_id=pair_id, collab_only=True, limit=limit
        )

    def list_public(self, pair_id: str, limit: int = 50) -> tuple[MessageView, ...]:
        """公开大屏投影：仅进行中的结对可读。

        未知或已结束的结对一律返回空数组，避免公开端成为历史消息的爬取入口，
        也不暴露「结对是否存在」的差异。
        """
        with self._uow() as uow:
            pair = uow.pairs.get(pair_id)
        if pair is None or pair.state != "active":
            return ()
        return self._messaging.list_collab(pair_id, limit)

    def _load(self, actor: Actor, pair_id: str) -> Pair:
        with self._uow() as uow:
            pair = uow.pairs.get(pair_id)
        if pair is None:
            raise NotFoundError("结对不存在")
        if Capability.ALL in actor.capabilities or pair.involves(actor.employee_id):
            return pair
        raise PermissionDeniedError("只能访问自己参与的结对")
