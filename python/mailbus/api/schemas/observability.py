"""overview / log / stream 的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MetricPointOut(BaseModel):
    metric: str
    value: int | float
    unit: str = "count"


class OverviewOut(BaseModel):
    employees_total: int
    employees_active: int
    employees_pending: int
    employees_offline: int
    agents_total: int
    agents_enabled: int
    agents_online: int
    agents_busy: int
    teams: int
    positions: int
    seats_occupied: int
    tasks_total: int
    tasks_active: int
    tasks_running: int
    tasks_blocked: int
    tasks_done: int
    tasks_failed_today: int
    approvals_pending: int
    messages_total: int
    skills_total: int
    skills_enabled: int
    workflows_total: int
    workflows_published: int
    metrics: list[MetricPointOut]


class LogEntryOut(BaseModel):
    event_id: str
    kind: str
    payload: dict[str, Any]
    attempts: int
    created_at: datetime | None = None
