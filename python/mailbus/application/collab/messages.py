"""协同消息用例：在结对范围内发送与检索消息。

消息本体仍写入 ``msg_messages``，这里只补 pair 维度的准入校验。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.identity.dto import Actor
from mailbus.application.messaging.dto import MessageView, SendMessageCommand
from mailbus.application.messaging.service import MessagingService
from mailbus.core.collab.models import Pair
from mailbus.core.collab.ports import CollabUnitOfWork
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
    ) -> None:
        self._messaging = messaging
        self._uow = uow_factory

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
        return self._messaging.send(
            actor,
            SendMessageCommand(
                body=body,
                recipient_id=recipient_id,
                kind=kind,
                channel=channel,
                pair_id=pair_id,
            ),
        )

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

    def _load(self, actor: Actor, pair_id: str) -> Pair:
        with self._uow() as uow:
            pair = uow.pairs.get(pair_id)
        if pair is None:
            raise NotFoundError("结对不存在")
        if Capability.ALL in actor.capabilities or pair.involves(actor.employee_id):
            return pair
        raise PermissionDeniedError("只能访问自己参与的结对")
