"""出站事件模型（outbox 行与投递结果）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """待投递事件。写入与业务状态变更在同一个事务里完成。"""

    event_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    due_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """领域事件：尚未分配 id，由 application 转成 outbox 行后随事务落库。"""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """一次投递尝试的结果；失败不改任务状态，只记录尝试。"""

    ok: bool
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class InboundEnvelope:
    """入站队列中的一条原始报文（如 file_bus 的一个文件）。"""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
