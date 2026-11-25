"""指标治理对外的仓储与清单端口（由 adapters 实现）。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.identity.ports import EmployeeRepository
from mailbus.core.metrics.models import MetricLayout, MetricRule
from mailbus.core.shared.ports import OutboxPort


class MetricRuleRepository(Protocol):
    def list_all(self) -> list[MetricRule]: ...

    def get(self, rule_id: str) -> MetricRule | None: ...

    def save(self, rule: MetricRule) -> None: ...


class MetricLayoutRepository(Protocol):
    def get(self) -> MetricLayout: ...

    def save(self, layout: MetricLayout) -> None: ...


class MetricReportRepository(Protocol):
    """报表聚合：调用方先按 data_scope 解析可见员工集合，再下推同一过滤。"""

    def task_summary(self, start: float, end: float, owners: tuple[str, ...] | None) -> dict: ...

    def task_timeline(
        self, start: float, end: float, owners: tuple[str, ...] | None
    ) -> list[tuple[float, float, str]]: ...

    def workflow_breakdown(
        self, start: float, end: float, owners: tuple[str, ...] | None
    ) -> list[tuple[str, str, int, int, int, float]]: ...

    def agent_breakdown(
        self, start: float, end: float, owners: tuple[str, ...] | None
    ) -> list[tuple[str, str, int, int, int]]: ...

    def online_agents(self, cutoff: float) -> int: ...


class MetricsManifestPort(Protocol):
    def read(self) -> dict:
        """读取指标口径清单（SoT：metrics-manifest.json）。"""


class MetricsUnitOfWork(Protocol):
    outbox: OutboxPort
    metric_rules: MetricRuleRepository
    metric_layout: MetricLayoutRepository
    reports: MetricReportRepository
    employees: EmployeeRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
