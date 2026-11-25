"""审计与告警路由：日志查询/CSV、告警确认、通知规则 CRUD/测试。"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import audit as mapper
from mailbus.api.schemas.audit import AuditStatsOut
from mailbus.api.schemas.contract.system import (
    AlertListOut,
    AlertOut,
    AlertRuleIn,
    AlertRuleListOut,
    AlertRuleOut,
    AlertRuleTestOut,
    AlertRuleUpdateIn,
    AuditEntryOut,
    AuditListOut,
)
from mailbus.application.ops.service import parse_time
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api", tags=["audit"])


def _ops(request: Request):
    return request.app.state.container.ops


def _audit_csv(request: Request, current, actor, action, resource, start, end):
    content = _ops(request).export_audit_csv(current, actor, action, resource, start, end)
    return StreamingResponse(
        iter([content]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )


def _audit_page(rows, total: int, limit: int, offset: int) -> AuditListOut:
    return AuditListOut(
        items=[AuditEntryOut(**asdict(entry)) for entry in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/tasks/audit/stats", response_model=AuditStatsOut, summary="审核统计")
def audit_stats(request: Request) -> AuditStatsOut:
    actor = get_actor(request)
    return mapper.to_audit_stats(request.app.state.container.audit.stats(actor))


@router.get("/audit", response_model=AuditListOut, summary="审计日志列表")
def list_audit(
    request: Request,
    actor: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    format: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    current = get_actor(request)
    service = _ops(request)
    start, end = parse_time(from_), parse_time(to)
    if format == "csv":
        return _audit_csv(request, current, actor, action, resource, start, end)
    rows, total = service.list_audit(
        current, actor, action, resource, start, end, limit, offset
    )
    return _audit_page(rows, total, limit, offset)


@router.get("/audit/{audit_id}", response_model=AuditEntryOut, summary="审计详情")
def get_audit(audit_id: int, request: Request) -> AuditEntryOut:
    entry = _ops(request).get_audit(get_actor(request), audit_id)
    return AuditEntryOut(**asdict(entry))


@router.get("/alerts", response_model=AlertListOut, summary="告警列表")
def alerts(
    request: Request,
    state: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AlertListOut:
    rows, total = _ops(request).list_alerts(
        get_actor(request), state, severity, limit, offset
    )
    return AlertListOut(
        items=[AlertOut(**asdict(alert)) for alert in rows],
        total=total, limit=limit, offset=offset,
    )


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut, summary="确认告警")
@declares(Capability.CONSOLE_ADMIN)
def ack_alert(alert_id: str, request: Request) -> AlertOut:
    alert = _ops(request).ack_alert(get_actor(request), alert_id)
    return AlertOut(**asdict(alert))


@router.get("/alert-rules", response_model=AlertRuleListOut, summary="告警规则列表")
def list_alert_rules(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AlertRuleListOut:
    rows, total = _ops(request).list_rules(get_actor(request), limit, offset)
    return AlertRuleListOut(
        items=[AlertRuleOut(**asdict(rule)) for rule in rows],
        total=total, limit=limit, offset=offset,
    )


@router.post(
    "/alert-rules", response_model=AlertRuleOut, status_code=201, summary="创建告警规则"
)
@declares(Capability.SYSTEM_CONFIG)
def create_alert_rule(payload: AlertRuleIn, request: Request) -> AlertRuleOut:
    rule = _ops(request).create_rule(get_actor(request), payload.model_dump())
    return AlertRuleOut(**asdict(rule))


@router.patch(
    "/alert-rules/{rule_id}", response_model=AlertRuleOut, summary="更新告警规则"
)
@declares(Capability.SYSTEM_CONFIG)
def update_alert_rule(
    rule_id: str, payload: AlertRuleUpdateIn, request: Request
) -> AlertRuleOut:
    changes = payload.model_dump(exclude_unset=True)
    rule = _ops(request).update_rule(get_actor(request), rule_id, changes)
    return AlertRuleOut(**asdict(rule))


@router.delete("/alert-rules/{rule_id}", status_code=204, summary="删除告警规则")
@declares(Capability.SYSTEM_CONFIG)
def delete_alert_rule(rule_id: str, request: Request) -> None:
    _ops(request).delete_rule(get_actor(request), rule_id)


@router.post(
    "/alert-rules/{rule_id}/test", response_model=AlertRuleTestOut, summary="测试告警规则"
)
@declares(Capability.SYSTEM_CONFIG)
def test_alert_rule(rule_id: str, request: Request) -> AlertRuleTestOut:
    result = _ops(request).test_rule(get_actor(request), rule_id)
    return AlertRuleTestOut(**result)
