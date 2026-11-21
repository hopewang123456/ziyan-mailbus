"""消息与收件箱的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# 接收人标识：限字符集与长度，避免路径穿越与超长目录名。
_RECIPIENT_ID = r"^[A-Za-z0-9_-]+$"


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    recipient_id: str | None = Field(default=None, max_length=64, pattern=_RECIPIENT_ID)
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


class PublicMessageOut(BaseModel):
    """公开协同消息投影：不暴露发送者与接收者身份。"""

    message_id: str
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
