"""指标治理用例：清单、查询、告警规则与大盘布局。"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.metrics.dto import (
    AlertView,
    MetricLayoutView,
    MetricPointView,
    MetricQueryView,
    MetricRuleView,
    MetricSeriesView,
)
from mailbus.application.queries.overview import OverviewQuery
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.metrics import rules
from mailbus.core.metrics.ports import MetricsManifestPort, MetricsUnitOfWork
from mailbus.core.shared.errors import NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability

_UNCOLLECTED = frozenset(
    {
        "tokens.today_estimated",
        "tasks.cycle_avg_minutes",
        "tasks.interventions_week",
        "bus.unread",
    }
)


class MetricsService:
    def __init__(
        self,
        uow_factory: Callable[[], MetricsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        manifest: MetricsManifestPort,
        overview: OverviewQuery,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._manifest = manifest
        self._overview = overview

    def manifest(self) -> dict:
        return self._manifest.read()

    def query(
        self, metrics: tuple[str, ...], granularity: str, hours: int
    ) -> MetricQueryView:
        catalog = {
            item["id"]: item
            for item in self._manifest.read().get("metrics", [])
            if isinstance(item, dict) and "id" in item
        }
        current = {item.metric: item for item in self._overview.get().metrics}
        ids = metrics or tuple(catalog)
        alert_count = len(self.alerts())
        points = tuple(
            _point(metric, catalog, current, alert_count) for metric in ids
        )
        series = (
            tuple(MetricSeriesView(metric, granularity, ()) for metric in ids)
            if metrics
            else ()
        )
        return MetricQueryView(points=points, series=series)

    def alerts(self) -> tuple[AlertView, ...]:
        """按启用的规则评估当前指标，生成只读告警视图。"""
        now = self._clock.now()
        with self._uow() as uow:
            rules = uow.metric_rules.list_all()
        current = {item.metric: item.value for item in self._overview.get().metrics}
        alerts = []
        for rule in rules:
            if not rule.enabled or rule.metric not in current:
                continue
            value = current[rule.metric]
            if not _triggered(value, rule.op, rule.threshold):
                continue
            message = rule.note or (
                f"{rule.metric} {rule.op} {rule.threshold:g}（当前 {value:g}）"
            )
            alerts.append(
                AlertView(
                    alert_id=rule.rule_id,
                    type=rule.metric,
                    severity=rule.severity,
                    message=message,
                    ts=now.isoformat(),
                )
            )
        return tuple(alerts)

    def list_rules(self) -> tuple[MetricRuleView, ...]:
        with self._uow() as uow:
            found = uow.metric_rules.list_all()
        return tuple(MetricRuleView.of(rule) for rule in found)

    def update_rule(
        self, actor: Actor, rule_id: str, changes: dict[str, object]
    ) -> MetricRuleView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            rule = uow.metric_rules.get(rule_id)
            if rule is None:
                raise NotFoundError("告警规则不存在")
            updated, events = rules.update_rule(rule, changes)
            uow.metric_rules.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return MetricRuleView.of(updated)

    def layout(self) -> MetricLayoutView:
        with self._uow() as uow:
            return MetricLayoutView.of(uow.metric_layout.get())

    def update_layout(self, actor: Actor, hidden: list[str]) -> MetricLayoutView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            updated, events = rules.update_layout(uow.metric_layout.get(), hidden)
            uow.metric_layout.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return MetricLayoutView.of(updated)

    @staticmethod
    def _require(actor: Actor) -> None:
        ensure_allowed(
            actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="metric")
        )


def _point(
    metric: str,
    catalog: dict[str, dict],
    current: dict,
    alert_count: int,
) -> MetricPointView:
    entry = catalog.get(metric, {})
    unit = str(entry.get("unit", "count"))
    if metric in current:
        return MetricPointView(metric, current[metric].value, unit)
    if metric == "alerts.active":
        return MetricPointView(metric, alert_count, unit)
    if metric in _UNCOLLECTED:
        return MetricPointView(metric, 0, unit, "未开始采集")
    if entry:
        return MetricPointView(metric, 0, unit, "指标未接入")
    return MetricPointView(metric, 0, unit, "未知指标")


def _triggered(value: float, op: str, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == "=":
        return value == threshold
    return value != threshold
