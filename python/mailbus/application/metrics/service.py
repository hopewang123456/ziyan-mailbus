"""指标治理用例：清单、查询、告警规则与大盘布局。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import csv
import io

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
from mailbus.core.agents import rules as agent_rules
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.metrics import rules
from mailbus.core.metrics.ports import MetricsManifestPort, MetricsUnitOfWork
from mailbus.core.shared.errors import NotFoundError, UnprocessableError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability, DataScope

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

    def overview_report(self, actor: Actor, from_: str | None, to: str | None) -> dict:
        start, end = _range(from_, to, self._clock.now())
        owners = self._visible_owners(actor)
        with self._uow() as uow:
            summary = uow.reports.task_summary(start, end, owners)
            online = uow.reports.online_agents(
                self._clock.now().timestamp() - agent_rules.heartbeat_timeout().total_seconds()
            )
        totals = {
            key: summary[key]
            for key in ("total", "done", "failed", "cancelled", "active", "queued")
        }
        return {
            "start": _iso(start), "end": _iso(end),
            "cards": _cards(summary, online), "totals": totals,
        }

    def trend_report(
        self, actor: Actor, metrics: tuple[str, ...], from_: str | None,
        to: str | None, bucket: str,
    ) -> dict:
        start, end = _range(from_, to, self._clock.now())
        step = _bucket_seconds(bucket)
        ids = metrics or ("tasks.created", "tasks.completed")
        unknown = set(ids) - {"tasks.created", "tasks.completed"}
        if unknown:
            raise UnprocessableError(f"不支持的趋势指标：{', '.join(sorted(unknown))}")
        owners = self._visible_owners(actor)
        with self._uow() as uow:
            timeline = uow.reports.task_timeline(start, end, owners)
        series = [
            {
                "metric": metric, "granularity": bucket,
                "points": _points(timeline, metric, start, end, step),
            }
            for metric in ids
        ]
        return {"start": _iso(start), "end": _iso(end), "bucket": bucket, "series": series}

    def breakdown_report(
        self, actor: Actor, metric: str | None, from_: str | None, to: str | None
    ) -> dict:
        metric = metric or "workflow_completion_rate"
        start, end = _range(from_, to, self._clock.now())
        owners = self._visible_owners(actor)
        with self._uow() as uow:
            if metric in ("workflow_completion_rate", "workflow_avg_duration"):
                rows = uow.reports.workflow_breakdown(start, end, owners)
                items = _workflow_items(metric, rows)
            elif metric in ("agent_load", "agent_failure_rate"):
                rows = uow.reports.agent_breakdown(start, end, owners)
                items = _agent_items(metric, rows)
            else:
                raise UnprocessableError(f"不支持的排行指标：{metric}")
        extras = {}
        for item in items:
            detail = item.pop("extra", None)
            if detail:
                extras[item["key"]] = detail
        items.sort(key=lambda item: item["value"], reverse=True)
        return {
            "start": _iso(start), "end": _iso(end), "metric": metric,
            "items": items, "extra": extras,
        }

    def export_csv(self, actor: Actor, from_: str | None, to: str | None) -> str:
        """与 overview/breakdown 复用同一 data_scope 过滤，不另做全量聚合后裁剪。"""
        overview = self.overview_report(actor, from_, to)
        workflows = self.breakdown_report(actor, "workflow_completion_rate", from_, to)
        agents = self.breakdown_report(actor, "agent_load", from_, to)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["section", "key", "label", "metric", "value", "unit"])
        for card in overview["cards"]:
            writer.writerow(["card", card["metric"], "", card["metric"],
                             card["value"], card["unit"]])
        for section, report in (("workflow", workflows), ("agent", agents)):
            for item in report["items"]:
                writer.writerow([section, item["key"], item["label"],
                                 report["metric"], item["value"], "count"])
        return "﻿" + buffer.getvalue()

    def _visible_owners(self, actor: Actor) -> tuple[str, ...] | None:
        """global 全量（None）；team 本队含本人；self 仅本人。"""
        if actor.data_scope is DataScope.GLOBAL:
            return None
        if actor.data_scope is DataScope.SELF:
            return (actor.employee_id,)
        with self._uow() as uow:
            employees = uow.employees.list_all()
        owners = {item.employee_id for item in employees if item.team_id == actor.team_id}
        owners.add(actor.employee_id)
        return tuple(sorted(owners))

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

    def get_rule(self, rule_id: str) -> MetricRuleView:
        with self._uow() as uow:
            rule = uow.metric_rules.get(rule_id)
        if rule is None:
            raise NotFoundError("告警规则不存在")
        return MetricRuleView.of(rule)

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


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _parse(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise UnprocessableError(f"时间格式不合法：{value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _range(from_: str | None, to: str | None, now: datetime) -> tuple[float, float]:
    end = _parse(to)
    if end is None:
        end = now.timestamp()
    start = _parse(from_)
    if start is None:
        start = (datetime.fromtimestamp(end, tz=timezone.utc) - timedelta(days=7)).timestamp()
    if start > end:
        raise UnprocessableError("from 不能晚于 to")
    return start, end


def _bucket_seconds(bucket: str) -> int:
    if bucket in ("1h", "hour"):
        return 3600
    if bucket in ("1d", "day"):
        return 86400
    raise UnprocessableError(f"不支持的 bucket：{bucket}")


def _cards(summary: dict, online_agents: int) -> list[dict]:
    total = summary["total"]
    done = summary["done"]
    failed = summary["failed"]
    completion = round(done / total * 100.0, 1) if total else 0.0
    failure = round(failed / total * 100.0, 1) if total else 0.0
    return [
        {"metric": "tasks.total", "value": total, "unit": "count"},
        {"metric": "tasks.running", "value": summary["active"], "unit": "count"},
        {"metric": "tasks.completion_rate", "value": completion, "unit": "percent"},
        {"metric": "tasks.avg_done_minutes", "value": summary["avg_done_minutes"],
         "unit": "minutes"},
        {"metric": "tasks.failure_rate", "value": failure, "unit": "percent"},
        {"metric": "tasks.escalations", "value": summary["escalations"], "unit": "count"},
        {"metric": "agents.online", "value": online_agents, "unit": "count"},
        {"metric": "tasks.backlog", "value": summary["queued"], "unit": "count"},
    ]


def _points(timeline, metric: str, start: float, end: float, step: int) -> list[dict]:
    counts: dict[int, int] = {}
    for created, updated, state in timeline:
        if metric == "tasks.created" and start <= created <= end:
            index = int((created - start) // step)
            counts[index] = counts.get(index, 0) + 1
        if metric == "tasks.completed" and state == "done" and start <= updated <= end:
            index = int((updated - start) // step)
            counts[index] = counts.get(index, 0) + 1
    buckets = max(1, int((end - start) // step) + 1)
    return [
        {"ts": _iso(start + index * step), "value": counts.get(index, 0)}
        for index in range(buckets)
    ]


def _workflow_items(metric: str, rows) -> list[dict]:
    items = []
    for workflow_id, name, total, done, failed, avg_done in rows:
        rate = round(done / total * 100.0, 1) if total else 0.0
        minutes = round(avg_done / 60.0, 1)
        value = rate if metric == "workflow_completion_rate" else minutes
        items.append({
            "key": workflow_id, "label": name or workflow_id, "value": value,
            "extra": {"total": total, "done": done, "failed": failed,
                      "avg_minutes": minutes},
        })
    return items


def _agent_items(metric: str, rows) -> list[dict]:
    items = []
    for employee_id, name, total, failed, active in rows:
        rate = round(failed / total * 100.0, 1) if total else 0.0
        value = total if metric == "agent_load" else rate
        items.append({
            "key": employee_id, "label": name or employee_id, "value": value,
            "extra": {"total": total, "failed": failed, "active": active},
        })
    return items
