"""指标治理对外的仓储与清单端口（由 adapters 实现）。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.metrics.models import MetricLayout, MetricRule
from mailbus.core.shared.ports import OutboxPort


class MetricRuleRepository(Protocol):
    def list_all(self) -> list[MetricRule]: ...

    def get(self, rule_id: str) -> MetricRule | None: ...

    def save(self, rule: MetricRule) -> None: ...


class MetricLayoutRepository(Protocol):
    def get(self) -> MetricLayout: ...

    def save(self, layout: MetricLayout) -> None: ...


class MetricsManifestPort(Protocol):
    def read(self) -> dict:
        """读取指标口径清单（SoT：metrics-manifest.json）。"""


class MetricsUnitOfWork(Protocol):
    outbox: OutboxPort
    metric_rules: MetricRuleRepository
    metric_layout: MetricLayoutRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
