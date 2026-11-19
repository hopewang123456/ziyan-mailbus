"""system 分组的对外模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    schema_version: int
    time: datetime
