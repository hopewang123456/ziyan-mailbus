"""协同上下文的领域模型：大屏与结对。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Pair:
    """两名员工之间的结对关系；结束只改状态，保留历史。"""

    pair_id: str
    initiator_id: str
    partner_id: str
    state: str
    created_at: datetime
    ended_at: datetime | None = None

    def involves(self, employee_id: str) -> bool:
        return employee_id in (self.initiator_id, self.partner_id)


@dataclass(frozen=True, slots=True)
class Screen:
    screen_id: str
    name: str
    floor_id: str | None
    seat_id: str | None
    online: bool
    last_seen_at: datetime | None
    created_at: datetime
    secret: str | None = None
