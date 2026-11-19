"""file_bus 入站用例：解析信封 → 令牌换 Actor → 与 HTTP 入口共用发送用例。

鉴权只在 MessagingService.send 里发生，本用例不重复判断权限。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from mailbus.application.identity.dto import Actor
from mailbus.application.messaging.dto import make_send_command
from mailbus.application.messaging.service import MessagingService
from mailbus.core.shared.errors import DomainError
from mailbus.core.shared.ports import InboundQueue

logger = logging.getLogger(__name__)


class FileBusIngress:
    def __init__(
        self,
        service: MessagingService,
        resolve_token: Callable[[str], Actor],
        queue: InboundQueue,
    ) -> None:
        self._service = service
        self._resolve = resolve_token
        self._queue = queue

    def poll_once(self) -> tuple[int, int]:
        """返回 (已受理, 已拒绝)；单条失败不影响其余报文。"""
        accepted = rejected = 0
        for envelope in self._queue.pending():
            try:
                actor = self._resolve(str(envelope.payload.get("token") or ""))
                self._service.send(
                    actor,
                    make_send_command(
                        body=str(envelope.payload.get("body") or ""),
                        recipient_id=_optional(envelope.payload.get("recipient_id")),
                        kind=str(envelope.payload.get("kind") or "note"),
                        channel=str(envelope.payload.get("channel") or "file_bus"),
                    ),
                )
            except DomainError as exc:
                self._queue.fail(envelope.name, exc.code)
                rejected += 1
            else:
                self._queue.complete(envelope.name)
                accepted += 1
        return accepted, rejected

    async def run(self, stop: asyncio.Event, interval: float = 5.0) -> None:
        while not stop.is_set():
            try:
                self.poll_once()
            except Exception:  # 单次扫描失败不能中断入站循环
                logger.exception("file_bus 入站扫描失败")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue


def _optional(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
