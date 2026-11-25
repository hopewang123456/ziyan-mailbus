"""大屏域契约模型：公开登记/心跳/配置/发布/聚焦与管理列表。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from mailbus.api.schemas.contract.common import Page

PlayState = Literal["playing", "paused"]
LayoutType = Literal["office", "grid", "custom"]
Theme = Literal["auto", "dark", "light"]
Resolution = Literal["1920x1080", "3840x2160"]


class ScreenRegisterIn(BaseModel):
    screen_id: str | None = Field(default=None, max_length=64)
    secret: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, max_length=64)
    floor_id: str | None = None
    seat_id: str | None = None


class ScreenRegisterOut(BaseModel):
    screen_id: str
    screen_secret: str | None = Field(
        default=None, description="仅首次自动登记返回，之后不可找回"
    )
    config_version: int


class ScreenHeartbeatIn(BaseModel):
    floor_id: str | None = None
    seat_id: str | None = None


class ScreenOut(BaseModel):
    screen_id: str
    name: str
    source: str
    online: bool
    last_seen_at: datetime | None = None
    config_version: int
    published_config_version: int | None = None
    team_bound: bool
    play_state: str = "playing"


class ScreenListOut(Page[ScreenOut]):
    pass


class ScreenConfigIn(BaseModel):
    layout_type: LayoutType = "office"
    theme: Theme = "auto"
    resolution: Resolution = "1920x1080"
    team_id: str | None = None
    office: dict[str, Any] | None = None
    grid: dict[str, Any] | None = None
    custom: dict[str, Any] | None = None


class ScreenDraftIn(BaseModel):
    config: ScreenConfigIn | None = None
    play_state: PlayState | None = None


class ScreenConfigOut(BaseModel):
    screen_id: str
    config_version: int
    published_config_version: int | None = None
    updated_at: datetime | None = None
    play_state: str = "playing"
    config: ScreenConfigIn | None = None


class PublicScreenConfigOut(BaseModel):
    """公开投影：不含 team_id，只给 team_bound。"""

    screen_id: str
    config_version: int
    published: bool
    layout_type: str
    theme: str
    resolution: str
    team_bound: bool
    play_state: str
    office: dict[str, Any] | None = None
    grid: dict[str, Any] | None = None
    custom: dict[str, Any] | None = None


class ScreenPublishIn(BaseModel):
    expected_config_version: int = Field(ge=1)


class ScreenPublishOut(BaseModel):
    config_version: int
    published_at: datetime | None = None


class ScreenFocusIn(BaseModel):
    floor_id: str = Field(min_length=1)
    seat_id: str | None = None
