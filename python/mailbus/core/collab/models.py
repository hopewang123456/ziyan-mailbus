"""协同上下文的领域模型：大屏与结对。"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    """一块自动登记或已被接管的物理大屏。

    密钥只保存不可逆哈希；明文仅在登记响应返回一次。
    配置分草稿``config``与已发布``published_config``，``config_version``只随发布 +1。
    """

    screen_id: str
    name: str
    source: str
    online: bool
    last_seen_at: datetime | None
    created_at: datetime
    config: dict = field(default_factory=dict)
    published_config: dict = field(default_factory=dict)
    config_version: int = 1
    updated_at: datetime | None = None
    secret_hash: str | None = None
