"""指标治理用例的输出模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mailbus.core.metrics.models import MetricLayout, MetricRule


@dataclass(frozen=True, slots=True)
class MetricRuleView:
    rule_id: str
    metric: str
    op: str
    threshold: float
    severity: str
    enabled: bool
    note: str
    actions: tuple[str, ...]

    @classmethod
    def of(cls, rule: MetricRule) -> "MetricRuleView":
        return cls(
            rule_id=rule.rule_id,
            metric=rule.metric,
            op=rule.op,
            threshold=rule.threshold,
            severity=rule.severity,
            enabled=rule.enabled,
            note=rule.note,
            actions=rule.actions,
        )


@dataclass(frozen=True, slots=True)
class MetricLayoutView:
    hidden: tuple[str, ...]

    @classmethod
    def of(cls, layout: MetricLayout) -> "MetricLayoutView":
        return cls(hidden=layout.hidden)


@dataclass(frozen=True, slots=True)
class MetricPointView:
    metric: str
    value: int | float
    unit: str = "count"
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MetricSeriesView:
    metric: str
    granularity: str
    points: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class MetricQueryView:
    points: tuple[MetricPointView, ...]
    series: tuple[MetricSeriesView, ...] = ()


@dataclass(frozen=True, slots=True)
class AlertView:
    alert_id: str
    type: str
    severity: str
    message: str
    ts: str
