"""审计与告警路由：审核统计与最近告警。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mailbus.api.deps import get_actor
from mailbus.api.mappers import audit as mapper
from mailbus.api.schemas.audit import AlertListOut, AuditStatsOut

router = APIRouter(prefix="/api", tags=["audit"])


@router.get(
    "/tasks/audit/stats", response_model=AuditStatsOut, summary="审核统计"
)
def audit_stats(request: Request) -> AuditStatsOut:
    get_actor(request)
    return mapper.to_audit_stats(request.app.state.container.audit.stats())


@router.get("/alerts", response_model=AlertListOut, summary="最近告警")
def alerts(request: Request) -> AlertListOut:
    get_actor(request)
    return mapper.to_alerts(request.app.state.container.audit.alerts())
