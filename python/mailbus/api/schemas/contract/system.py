"""系统域契约模型：审计、告警、告警规则。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from mailbus.api.schemas.contract.common import Page

AlertSeverity = Literal["info", "warn", "critical"]
AlertStatus = Literal["firing", "acked", "resolved"]


class AuditEntryOut(BaseModel):
    audit_id: int
    actor_id: str | None = None
    action: str
    resource: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AuditListOut(Page[AuditEntryOut]):
    pass


class AlertOut(BaseModel):
    alert_id: str
    rule_id: str | None = None
    type: str
    severity: str
    resource_type: str | None = None
    resource_id: str | None = None
    status: str
    value: str | None = None
    threshold: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    acked_by: str | None = None
    acked_at: datetime | None = None
    resolved_at: datetime | None = None


class AlertListOut(Page[AlertOut]):
    pass


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    alert_type: str = Field(min_length=1, max_length=64)
    threshold: float | None = None
    channel: Literal["webhook", "email", "inapp"] = "inapp"
    target: str | None = None
    silence_seconds: int = Field(default=300, ge=0)
    enabled: bool = True


class AlertRuleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    alert_type: str | None = None
    threshold: float | None = None
    channel: Literal["webhook", "email", "inapp"] | None = None
    target: str | None = None
    silence_seconds: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class AlertRuleOut(BaseModel):
    rule_id: str
    name: str
    alert_type: str
    threshold: float | None = None
    channel: str
    target: str | None = None
    silence_seconds: int = 300
    enabled: bool
    created_by: str | None = None
    created_at: datetime | None = None


class AlertRuleListOut(Page[AlertRuleOut]):
    pass


class AlertRuleTestOut(BaseModel):
    rule_id: str
    ok: bool
    message_zh: str


class IntegrationInvokeOut(BaseModel):
    name: str
    action: str
    result: dict[str, Any] = Field(default_factory=dict)
