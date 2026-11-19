"""审计与告警协议模型的映射。"""

from __future__ import annotations

from mailbus.api.schemas.audit import AlertListOut, AlertOut, AuditStatsOut
from mailbus.application.metrics.dto import AlertView
from mailbus.application.queries.audit import AuditStatsView


def to_audit_stats(view: AuditStatsView) -> AuditStatsOut:
    return AuditStatsOut(
        total_tasks=view.total_tasks,
        audited_tasks=view.audited_tasks,
        pending_audit_tasks=view.pending_audit_tasks,
        pass_count=view.pass_count,
        fail_count=view.fail_count,
        warn_count=view.warn_count,
        by_reviewer={
            reviewer: {
                "pass": stat.pass_count,
                "fail": stat.fail_count,
                "warn": stat.warn_count,
                "total": stat.total,
            }
            for reviewer, stat in view.by_reviewer.items()
        },
    )


def to_alerts(views: tuple[AlertView, ...]) -> AlertListOut:
    return AlertListOut(
        alerts=[
            AlertOut(
                id=item.alert_id,
                type=item.type,
                severity=item.severity,
                message=item.message,
                ts=item.ts,
            )
            for item in views
        ]
    )
