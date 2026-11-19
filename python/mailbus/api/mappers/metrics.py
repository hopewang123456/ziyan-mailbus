"""指标协议模型的映射。"""

from __future__ import annotations

from mailbus.api.schemas.metrics import (
    MetricLayoutOut,
    MetricLayoutViewOut,
    MetricPointOut,
    MetricQueryOut,
    MetricRuleOut,
    MetricSeriesOut,
)
from mailbus.application.metrics.dto import (
    MetricLayoutView,
    MetricPointView,
    MetricQueryView,
    MetricRuleView,
    MetricSeriesView,
)


def to_point(view: MetricPointView) -> MetricPointOut:
    return MetricPointOut(
        metric=view.metric,
        value=view.value,
        unit=view.unit,
        error=view.error,
    )


def to_series(view: MetricSeriesView) -> MetricSeriesOut:
    return MetricSeriesOut(
        metric=view.metric,
        granularity=view.granularity,
        points=list(view.points),
    )


def to_query(view: MetricQueryView) -> MetricQueryOut:
    return MetricQueryOut(
        points=[to_point(item) for item in view.points],
        series=[to_series(item) for item in view.series],
    )


def to_rule(view: MetricRuleView) -> MetricRuleOut:
    return MetricRuleOut(
        id=view.rule_id,
        metric=view.metric,
        op=view.op,
        threshold=view.threshold,
        severity=view.severity,
        enabled=view.enabled,
        note=view.note,
        actions=list(view.actions),
    )


def to_layout(view: MetricLayoutView) -> MetricLayoutViewOut:
    return MetricLayoutViewOut(layout=MetricLayoutOut(hidden=list(view.hidden)))
