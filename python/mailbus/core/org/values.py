"""组织上下文的枚举。"""

from __future__ import annotations

from enum import Enum


class RoomKind(str, Enum):
    """房间类型，必须与前端 ``web/src/twin/types.ts`` 保持一致。"""

    RECEPTION = "reception"
    BULLPEN = "bullpen"
    FOCUS = "focus"
    MEETING = "meeting"
    LOUNGE = "lounge"
