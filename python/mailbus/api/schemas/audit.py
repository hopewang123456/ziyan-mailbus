"""审计与告警的对外模型。"""

from __future__ import annotations

from pydantic import BaseModel


class AuditStatsOut(BaseModel):
    total_tasks: int
    audited_tasks: int
    pending_audit_tasks: int
    pass_count: int
    fail_count: int
    warn_count: int
    by_reviewer: dict[str, dict[str, int]]


class AlertOut(BaseModel):
    id: str
    type: str
    severity: str
    agent: str = ""
    message: str
    ts: str | None = None


class AlertListOut(BaseModel):
    alerts: list[AlertOut]
