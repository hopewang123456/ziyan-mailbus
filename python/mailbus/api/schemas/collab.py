"""大屏登记、结对与协同消息的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PairIn(BaseModel):
    partner_id: str = Field(min_length=1, max_length=64)


class PairOut(BaseModel):
    pair_id: str
    initiator_id: str
    partner_id: str
    state: str
    created_at: datetime
    ended_at: datetime | None = None


_RECIPIENT_ID = r"^[A-Za-z0-9_-]+$"


class CollabMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    pair_id: str = Field(min_length=1, max_length=64)
    recipient_id: str | None = Field(default=None, max_length=64, pattern=_RECIPIENT_ID)
    kind: str = Field(default="note", max_length=32)
    channel: Literal["file_bus", "a2a", "mcp"] = "file_bus"


class ScreenIn(BaseModel):
    screen_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    floor_id: str | None = None
    seat_id: str | None = None


class PublicScreenIn(BaseModel):
    screen_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    floor_id: str | None = None
    seat_id: str | None = None


_SECRET_ID = r"^[A-Za-z0-9_-]+$"


class ScreenHeartbeatIn(BaseModel):
    floor_id: str | None = None
    seat_id: str | None = None
    secret: str | None = Field(default=None, max_length=64, pattern=_SECRET_ID)


class ScreenLeaveIn(BaseModel):
    secret: str | None = Field(default=None, max_length=64, pattern=_SECRET_ID)


class ScreenFocusIn(BaseModel):
    floor_id: str = Field(min_length=1)
    seat_id: str | None = None


class ScreenOut(BaseModel):
    screen_id: str
    name: str
    floor_id: str | None
    seat_id: str | None
    online: bool
    last_seen: datetime | None
    secret: str | None = None


class OkOut(BaseModel):
    ok: bool = True
