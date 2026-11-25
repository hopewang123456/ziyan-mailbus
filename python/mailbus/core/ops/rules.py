"""告警规则校验、状态流转与冷却判定（纯函数）。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from mailbus.core.ops.models import Alert, AlertRule
from mailbus.core.shared.errors import InvalidStateError, UnprocessableError

AGENT_OFFLINE = "agent_offline"
RUN_TIMEOUT = "run_timeout"
ESCALATION_PENDING = "escalation_pending"
OUTBOX_BACKLOG = "outbox_backlog"
WORKFLOW_FAILURE_RATE = "workflow_failure_rate"

ALERT_TYPES = (
    AGENT_OFFLINE,
    RUN_TIMEOUT,
    ESCALATION_PENDING,
    OUTBOX_BACKLOG,
    WORKFLOW_FAILURE_RATE,
)

# 预置告警默认阈值：秒 / 条 / 百分比。
DEFAULT_THRESHOLDS = {
    AGENT_OFFLINE: 300.0,
    RUN_TIMEOUT: 3600.0,
    ESCALATION_PENDING: 3600.0,
    OUTBOX_BACKLOG: 100.0,
    WORKFLOW_FAILURE_RATE: 20.0,
}

SEVERITIES = {
    AGENT_OFFLINE: "warn",
    RUN_TIMEOUT: "warn",
    ESCALATION_PENDING: "info",
    OUTBOX_BACKLOG: "warn",
    WORKFLOW_FAILURE_RATE: "critical",
}

CHANNELS = ("webhook", "email", "inapp")


def normalize_rule(
    alert_type: str,
    channel: str,
    threshold: float | None,
    silence_seconds: int,
) -> float:
    """校验告警类型与渠道，返回生效阈值（未填时用预置默认值）。"""
    if alert_type not in ALERT_TYPES:
        raise UnprocessableError(f"不支持的告警类型：{alert_type}")
    if channel not in CHANNELS:
        raise UnprocessableError(f"不支持的通知渠道：{channel}")
    if silence_seconds < 0:
        raise UnprocessableError("silence_seconds 不能为负数")
    value = DEFAULT_THRESHOLDS[alert_type] if threshold is None else threshold
    if value < 0:
        raise UnprocessableError("阈值不能为负数")
    return float(value)


def severity_of(alert_type: str) -> str:
    return SEVERITIES.get(alert_type, "warn")


def ack(alert: Alert, actor_id: str, now: datetime) -> Alert:
    """firing → acked；已确认幂等；已恢复不可确认。"""
    if alert.status == "resolved":
        raise InvalidStateError("告警已恢复，无需确认")
    if alert.status == "acked":
        return alert
    return replace(alert, status="acked", acked_by=actor_id, acked_at=now)


def should_notify(last_sent: datetime | None, now: datetime, silence_seconds: int) -> bool:
    """冷却含义：同一规则、同一资源两次通知的最小间隔。"""
    if last_sent is None:
        return True
    return (now - last_sent).total_seconds() >= silence_seconds


def diff_detail(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """字段级 diff：仅在审计 detail 同时携带 before/after 对象时计算。"""
    before = detail.get("before")
    after = detail.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    changes = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes.append({"field": key, "before": old, "after": new})
    return changes
