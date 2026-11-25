"""消息上下文对外的仓储端口。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Self

from mailbus.core.messaging.models import DeliveryAttempt, Message
from mailbus.core.shared.ports import OutboxPort


class MessageRepository(Protocol):
    def add(self, message: Message) -> None: ...

    def get(self, message_id: str) -> Message | None: ...

    def inbox(
        self, recipient_id: str, limit: int | None = None, offset: int = 0
    ) -> list[Message]:
        """接收人可见的消息投影：指名消息 + 广播，按时间倒序分页。"""

    def list_all(self, limit: int = 200) -> list[Message]: ...

    def search(
        self,
        *,
        viewer_id: str | None = None,
        agent: str | None = None,
        employee_id: str | None = None,
        channel: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        pair_id: str | None = None,
        collab_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[Message, str]]:
        """按条件检索，返回 (消息, 最近投递状态)；viewer_id=None 表示不限可见范围。"""

    def count_search(
        self,
        *,
        viewer_id: str | None = None,
        agent: str | None = None,
        employee_id: str | None = None,
        channel: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        pair_id: str | None = None,
        collab_only: bool = False,
    ) -> int: ...

    def count(self) -> int: ...

    def delete(self, message_id: str) -> None:
        """删除消息及其投递尝试；由用例层先校验存在与权限。"""

    def add_attempt(
        self,
        message_id: str,
        *,
        ok: bool,
        error_code: str | None,
        detail: str | None,
        at: datetime,
    ) -> DeliveryAttempt: ...

    def attempts(self, message_id: str) -> list[DeliveryAttempt]: ...


class MessagingUnitOfWork(Protocol):
    outbox: OutboxPort
    messages: MessageRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
