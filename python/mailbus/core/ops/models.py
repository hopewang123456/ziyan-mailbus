"""审计与告警的纯领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEntry:
    audit_id: int
    actor_id: str | None
    action: str
    resource: str | None
    detail: dict[str, Any]
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class AlertRule:
    rule_id: str
    name: str
    alert_type: str
    threshold: float | None
    channel: str
    target: str | None
    silence_seconds: int
    enabled: bool
    created_by: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Alert:
    alert_id: str
    rule_id: str | None
    type: str
    severity: str
    resource_type: str | None
    resource_id: str | None
    status: str
    value: str | None
    threshold: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    acked_by: str | None = None
    acked_at: datetime | None = None
    resolved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Breach:
    """一次评估发现的越界对象：同一规则按资源维度各生成一条告警。"""

    resource_type: str
    resource_id: str
    value: str
    threshold: str
