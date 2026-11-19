"""消息与投递尝试。

消息是唯一写聚合；收件箱是按接收人过滤的只读投影，不落独立表。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Message:
    message_id: str
    sender_id: str
    body: str
    kind: str = "note"
    recipient_id: str | None = None
    created_at: datetime | None = None
    channel: str = "file_bus"
    pair_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    message_id: str
    attempt_no: int
    ok: bool
    error_code: str | None = None
    detail: str | None = None
    at: datetime | None = None
