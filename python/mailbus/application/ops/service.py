"""运维用例：审计查询/导出、告警确认、通知规则 CRUD 与周期评估。"""

from __future__ import annotations

import csv
import io
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from mailbus.application.identity.dto import Actor
from mailbus.core.identity.policy import Resource, ensure_any_allowed
from mailbus.core.ops import rules as ops_rules
from mailbus.core.ops.models import Alert, AlertRule, AuditEntry, Breach
from mailbus.core.ops.ports import AlertNotifierPort, OpsUnitOfWork
from mailbus.core.shared.errors import NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability

_LOG = logging.getLogger(__name__)
_EXPORT_LIMIT = 5000
_NOTIFY_ATTEMPTS = 3
_BACKOFF_BASE_SEC = 0.5


def parse_time(value: str | None) -> float | None:
    """ISO 8601 → epoch 秒；空值返回 None。"""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


class OpsService:
    def __init__(
        self,
        uow_factory: Callable[[], OpsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        notifier: AlertNotifierPort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._notifier = notifier

    # ---- 审计 ----

    def list_audit(
        self, actor: Actor, actor_id, action, resource, start, end, limit, offset
    ) -> tuple[tuple[AuditEntry, ...], int]:
        _require_log(actor)
        with self._uow() as uow:
            rows = uow.ops.list_audit(actor_id, action, resource, start, end, limit, offset)
            total = uow.ops.count_audit(actor_id, action, resource, start, end)
        return tuple(rows), total

    def get_audit(self, actor: Actor, audit_id: int) -> AuditEntry:
        _require_log(actor)
        with self._uow() as uow:
            entry = uow.ops.get_audit(audit_id)
        if entry is None:
            raise NotFoundError("审计记录不存在")
        diff = ops_rules.diff_detail(entry.detail)
        detail = {**entry.detail, "diff": diff} if diff else entry.detail
        return replace(entry, detail=detail)

    def export_audit_csv(self, actor: Actor, actor_id, action, resource, start, end) -> str:
        _require_log(actor)
        with self._uow() as uow:
            rows = uow.ops.list_audit(
                actor_id, action, resource, start, end, _EXPORT_LIMIT, 0
            )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["audit_id", "created_at", "actor_id", "action", "resource", "detail"])
        for entry in rows:
            writer.writerow([
                entry.audit_id,
                entry.created_at.isoformat() if entry.created_at else "",
                entry.actor_id or "",
                entry.action,
                entry.resource or "",
                entry.detail,
            ])
        return "﻿" + buffer.getvalue()

    # ---- 告警 ----

    def list_alerts(self, actor: Actor, state, severity, limit, offset):
        _require_log(actor)
        with self._uow() as uow:
            rows = uow.ops.list_alerts(state, severity, limit, offset)
            total = uow.ops.count_alerts(state, severity)
        return tuple(rows), total

    def ack_alert(self, actor: Actor, alert_id: str) -> Alert:
        _require_log(actor)
        now = self._clock.now()
        with self._uow() as uow:
            alert = uow.ops.get_alert(alert_id)
            if alert is None:
                raise NotFoundError("告警不存在")
            updated = ops_rules.ack(alert, actor.employee_id, now)
            uow.ops.save_alert(updated)
            uow.audit.record(actor.employee_id, "alert.acked", alert_id, {})
            uow.commit()
        return updated

    # ---- 通知规则 ----

    def list_rules(self, actor: Actor, limit: int, offset: int):
        _require_admin(actor)
        with self._uow() as uow:
            return tuple(uow.ops.list_rules(limit, offset)), uow.ops.count_rules()

    def create_rule(self, actor: Actor, payload: dict) -> AlertRule:
        _require_admin(actor)
        threshold = ops_rules.normalize_rule(
            payload["alert_type"], payload["channel"],
            payload.get("threshold"), payload.get("silence_seconds", 300),
        )
        rule = AlertRule(
            rule_id=self._ids.new("alr"), name=payload["name"].strip(),
            alert_type=payload["alert_type"], threshold=threshold,
            channel=payload["channel"], target=payload.get("target"),
            silence_seconds=payload.get("silence_seconds", 300),
            enabled=payload.get("enabled", True), created_by=actor.employee_id,
            created_at=self._clock.now(),
        )
        self._save_rule(actor, rule, "alert_rule.created")
        return rule

    def update_rule(self, actor: Actor, rule_id: str, changes: dict) -> AlertRule:
        _require_admin(actor)
        with self._uow() as uow:
            current = uow.ops.get_rule(rule_id)
        if current is None:
            raise NotFoundError("告警规则不存在")
        merged = {
            "alert_type": changes.get("alert_type") or current.alert_type,
            "channel": changes.get("channel") or current.channel,
            "threshold": changes.get("threshold")
            if changes.get("threshold") is not None else current.threshold,
            "silence_seconds": changes.get("silence_seconds")
            if changes.get("silence_seconds") is not None else current.silence_seconds,
        }
        threshold = ops_rules.normalize_rule(
            merged["alert_type"], merged["channel"], merged["threshold"],
            merged["silence_seconds"],
        )
        rule = replace(
            current, name=(changes.get("name") or current.name).strip(),
            alert_type=merged["alert_type"], channel=merged["channel"], threshold=threshold,
            target=changes.get("target", current.target),
            silence_seconds=merged["silence_seconds"],
            enabled=current.enabled if changes.get("enabled") is None else changes["enabled"],
        )
        self._save_rule(actor, rule, "alert_rule.updated")
        return rule

    def delete_rule(self, actor: Actor, rule_id: str) -> None:
        _require_admin(actor)
        with self._uow() as uow:
            if uow.ops.get_rule(rule_id) is None:
                raise NotFoundError("告警规则不存在")
            uow.ops.delete_rule(rule_id)
            uow.audit.record(actor.employee_id, "alert_rule.deleted", rule_id, {})
            uow.commit()

    def test_rule(self, actor: Actor, rule_id: str) -> dict:
        _require_admin(actor)
        with self._uow() as uow:
            rule = uow.ops.get_rule(rule_id)
        if rule is None:
            raise NotFoundError("告警规则不存在")
        payload = {
            "rule_id": rule.rule_id, "type": rule.alert_type, "test": True,
            "at": self._clock.now().isoformat(),
        }
        ok, attempts, error = self._deliver(rule.channel, rule.target, payload)
        with self._uow() as uow:
            uow.audit.record(actor.employee_id, "alert_rule.tested", rule_id,
                             {"ok": ok, "attempts": attempts, "error": error})
            uow.commit()
        return {
            "rule_id": rule_id, "ok": ok,
            "message_zh": "测试通知已发送" if ok else f"测试通知发送失败：{error}",
        }

    # ---- 周期评估 ----

    def evaluate(self, now: datetime | None = None) -> int:
        now = now or self._clock.now()
        with self._uow() as uow:
            enabled = uow.ops.list_enabled_rules()
        created = 0
        for rule in enabled:
            try:
                created += self._evaluate_rule(rule, now)
            except Exception:  # 单条规则失败不阻断其它规则
                _LOG.exception("alert rule evaluation failed: %s", rule.rule_id)
        return created

    def _evaluate_rule(self, rule: AlertRule, now: datetime) -> int:
        with self._uow() as uow:
            breaches = _breaches(uow.ops, rule, now)
            active = {item.resource_id: item for item in uow.ops.active_alerts(rule.rule_id)}
            fresh: list[Alert] = []
            seen: set[str] = set()
            for breach in breaches:
                seen.add(breach.resource_id)
                existing = active.get(breach.resource_id)
                if existing is None:
                    alert = _new_alert(self._ids, rule, breach, now)
                    fresh.append(alert)
                else:
                    alert = replace(existing, value=breach.value,
                                    threshold=breach.threshold, last_seen_at=now)
                uow.ops.save_alert(alert)
            for resource_id, existing in active.items():
                if resource_id not in seen:
                    uow.ops.save_alert(replace(
                        existing, status="resolved", resolved_at=now, last_seen_at=now,
                    ))
            uow.commit()
        for alert in fresh:
            self._notify(rule, alert, now)
        return len(fresh)

    def _notify(self, rule: AlertRule, alert: Alert, now: datetime) -> None:
        resource = f"{rule.rule_id}:{alert.resource_type}:{alert.resource_id}"
        with self._uow() as uow:
            last = uow.ops.last_notification(resource)
        if not ops_rules.should_notify(last, now, rule.silence_seconds):
            return
        payload = {
            "alert_id": alert.alert_id, "rule_id": rule.rule_id, "type": alert.type,
            "severity": alert.severity, "resource_type": alert.resource_type,
            "resource_id": alert.resource_id, "value": alert.value,
            "threshold": alert.threshold, "at": now.isoformat(),
        }
        ok, attempts, error = self._deliver(rule.channel, rule.target, payload)
        with self._uow() as uow:
            uow.audit.record(None, "alert.notified", resource, {
                "alert_id": alert.alert_id, "channel": rule.channel,
                "target": rule.target, "ok": ok, "attempts": attempts, "error": error,
            })
            uow.commit()

    def _deliver(self, channel: str, target: str | None, payload: dict):
        error = None
        for attempt in range(1, _NOTIFY_ATTEMPTS + 1):
            try:
                self._notifier.send(channel, target, payload)
                return True, attempt, None
            except Exception as exc:  # 重试后仍失败则写审计
                error = str(exc) or exc.__class__.__name__
                if attempt < _NOTIFY_ATTEMPTS:
                    time.sleep(_BACKOFF_BASE_SEC * (2 ** (attempt - 1)))
        return False, _NOTIFY_ATTEMPTS, error

    def _save_rule(self, actor: Actor, rule: AlertRule, action: str) -> None:
        with self._uow() as uow:
            uow.ops.save_rule(rule)
            uow.audit.record(actor.employee_id, action, rule.rule_id,
                             {"alert_type": rule.alert_type, "enabled": rule.enabled})
            uow.commit()


def _require_log(actor: Actor) -> None:
    ensure_any_allowed(
        actor.to_subject(), (Capability.LOG_READ, Capability.CONSOLE_ADMIN),
        Resource(kind="audit"),
    )


def _require_admin(actor: Actor) -> None:
    ensure_any_allowed(
        actor.to_subject(), (Capability.CONSOLE_ADMIN, Capability.SYSTEM_CONFIG),
        Resource(kind="alert_rule"),
    )


def _new_alert(ids: IdGenerator, rule: AlertRule, breach: Breach, now: datetime) -> Alert:
    return Alert(
        alert_id=ids.new("alert"), rule_id=rule.rule_id, type=rule.alert_type,
        severity=ops_rules.severity_of(rule.alert_type),
        resource_type=breach.resource_type, resource_id=breach.resource_id,
        status="firing", value=breach.value, threshold=breach.threshold,
        first_seen_at=now, last_seen_at=now,
    )


def _breaches(ops, rule: AlertRule, now: datetime) -> list[Breach]:
    threshold = rule.threshold or 0.0
    kind = rule.alert_type
    if kind == ops_rules.OUTBOX_BACKLOG:
        count = ops.outbox_backlog()
        if count > threshold:
            return [Breach("outbox", "outbox", str(count), f"{threshold:g}")]
        return []
    if kind == ops_rules.WORKFLOW_FAILURE_RATE:
        return _failure_breaches(ops, threshold, now.timestamp() - 3600.0)
    cutoff = now.timestamp() - threshold
    if kind == ops_rules.AGENT_OFFLINE:
        return [
            Breach("agent", agent_id, f"{(now.timestamp() - seen) / 60:.1f}min", f"{threshold:g}s")
            for agent_id, _name, seen in ops.offline_agents(cutoff)
        ]
    if kind == ops_rules.RUN_TIMEOUT:
        return [
            Breach("run", run_id, f"{(now.timestamp() - started) / 60:.1f}min", f"{threshold:g}s")
            for run_id, _task_id, started in ops.timed_out_runs(cutoff)
        ]
    return [
        Breach("escalation", escalation_id, f"{(now.timestamp() - created) / 60:.1f}min",
               f"{threshold:g}s")
        for escalation_id, _task_id, created in ops.stale_escalations(cutoff)
    ]


def _failure_breaches(ops, threshold: float, since: float) -> list[Breach]:
    breaches = []
    for workflow_id, _name, total, failed in ops.workflow_failures(since):
        if total <= 0:
            continue
        rate = failed / total * 100.0
        if rate > threshold:
            breaches.append(Breach("workflow", workflow_id, f"{rate:.1f}%", f"{threshold:g}%"))
    return breaches
