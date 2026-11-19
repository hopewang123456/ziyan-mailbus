"""出站端口（由 adapters 实现，application 只依赖协议）。

时钟与 id 生成必须注入：领域层不允许直调 time.time() 或 uuid。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Self

from .events import DeliveryResult, InboundEnvelope, OutboxEvent


class Clock(Protocol):
    def now(self) -> datetime:
        """当前时刻（带时区的 UTC）。"""


class IdGenerator(Protocol):
    def new(self, prefix: str) -> str:
        """生成带前缀的唯一 id。"""


class OutboxPort(Protocol):
    def enqueue(self, event: OutboxEvent) -> None:
        """写入待投递事件；与业务状态变更处于同一事务。"""

    def claim_due(self, limit: int) -> list[OutboxEvent]:
        """取出到期未投递事件（同一事件不会被两个派发器同时取走）。"""

    def mark_sent(self, event_id: str) -> None:
        """标记投递成功。"""

    def mark_failed(self, event_id: str, error_code: str) -> None:
        """记录一次失败；是否重排由实现按 attempts 决定。"""

    def mark_dead(self, event_id: str, error_code: str) -> None:
        """重试耗尽：终止投递，保留最后一次错误。"""

    def recent(self, limit: int) -> list[OutboxEvent]:
        """最近的出站事件（只读投影，用于操作日志）。"""


class InboundQueue(Protocol):
    """入站报文队列（file_bus 等本地通道）。"""

    def pending(self) -> list[InboundEnvelope]: ...

    def complete(self, name: str) -> None: ...

    def fail(self, name: str, error_code: str) -> None: ...


class UnitOfWork(Protocol):
    """一个用例 = 一个事务；路径与连接只由 bootstrap 提供。"""

    outbox: OutboxPort

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...


class Transport(Protocol):
    def send(self, event: OutboxEvent) -> DeliveryResult:
        """把事件投递给下游（A2A / MCP / 文件总线）。"""
