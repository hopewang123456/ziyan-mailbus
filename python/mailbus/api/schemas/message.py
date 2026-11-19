"""消息与收件箱的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    recipient_id: str | None = None
    kind: str = Field(default="note", max_length=32)
    channel: Literal["file_bus", "a2a", "mcp"] = "file_bus"


class MessageOut(BaseModel):
    message_id: str
    sender_id: str
    recipient_id: str | None = None
    kind: str
    body: str
    created_at: datetime | None = None
    delivery_status: str | None = None
    pair_id: str | None = None


class DeliveryAttemptOut(BaseModel):
    message_id: str
    attempt_no: int
    ok: bool
    error_code: str | None = None
    detail: str | None = None
    at: datetime | None = None
