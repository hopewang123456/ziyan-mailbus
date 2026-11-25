"""消息域契约模型：列表、发送、详情与追迹。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from mailbus.api.schemas.contract.common import Page

Channel = Literal["file_bus", "a2a", "mcp"]


class MessageOut(BaseModel):
    message_id: str
    sender_id: str
    recipient_id: str | None = None
    kind: str
    body: str
    channel: str = "file_bus"
    pair_id: str | None = None
    task_id: str | None = None
    delivery_status: str | None = None
    created_at: datetime | None = None


class MessageListOut(Page[MessageOut]):
    pass


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    recipient_id: str | None = Field(default=None, max_length=64)
    kind: str = Field(default="note", max_length=32)
    channel: Channel = "file_bus"


class MessageTraceEventOut(BaseModel):
    at: datetime | None = None
    status: str
    attempt_no: int | None = None
    channel: str | None = None
    error_code: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class MessageTraceOut(BaseModel):
    message_id: str
    events: list[MessageTraceEventOut] = Field(default_factory=list)
