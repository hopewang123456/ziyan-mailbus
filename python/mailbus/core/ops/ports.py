"""运维域仓储与通知端口（由 adapters 实现）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Self

from mailbus.core.ops.models import Alert, AlertRule, AuditEntry
from mailbus.core.shared.ports import AuditPort


class OpsRepository(Protocol):
    """审计查询、告警与通知规则、评估所需的只读聚合。"""

    # ---- 审计 ----
    def list_audit(
        self,
        actor: str | None,
        action: str | None,
        resource: str | None,
        start: float | None,
        end: float | None,
        limit: int,
        offset: int,
    ) -> list[AuditEntry]: ...

    def count_audit(
        self,
        actor: str | None,
        action: str | None,
        resource: str | None,
        start: float | None,
        end: float | None,
    ) -> int: ...

    def get_audit(self, audit_id: int) -> AuditEntry | None: ...

    # ---- 通知规则 ----
    def list_rules(self, limit: int, offset: int) -> list[AlertRule]: ...

    def count_rules(self) -> int: ...

    def list_enabled_rules(self) -> list[AlertRule]: ...

    def get_rule(self, rule_id: str) -> AlertRule | None: ...

    def save_rule(self, rule: AlertRule) -> None: ...

    def delete_rule(self, rule_id: str) -> None: ...

    # ---- 告警 ----
    def list_alerts(
        self, state: str | None, severity: str | None, limit: int, offset: int
    ) -> list[Alert]: ...

    def count_alerts(self, state: str | None, severity: str | None) -> int: ...

    def get_alert(self, alert_id: str) -> Alert | None: ...

    def save_alert(self, alert: Alert) -> None: ...

    def active_alerts(self, rule_id: str) -> list[Alert]: ...

    # ---- 通知冷却与评估数据 ----
    def last_notification(self, resource: str) -> datetime | None: ...

    def offline_agents(self, cutoff: float) -> list[tuple[str, str, float]]: ...

    def timed_out_runs(self, cutoff: float) -> list[tuple[str, str, float]]: ...

    def stale_escalations(self, cutoff: float) -> list[tuple[str, str, float]]: ...

    def outbox_backlog(self) -> int: ...

    def workflow_failures(self, since: float) -> list[tuple[str, str, int, int]]: ...


class AlertNotifierPort(Protocol):
    def send(self, channel: str, target: str | None, payload: dict[str, Any]) -> None:
        """单次投递（5 秒超时）；失败抛异常，由应用层重试并写审计。"""


class OpsUnitOfWork(Protocol):
    ops: OpsRepository
    audit: AuditPort

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
