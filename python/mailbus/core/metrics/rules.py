"""指标治理的纯函数状态转移。"""

from __future__ import annotations

from dataclasses import replace

from mailbus.core.metrics.models import MetricLayout, MetricRule
from mailbus.core.shared.errors import InvalidStateError
from mailbus.core.shared.events import DomainEvent

PATCHABLE_FIELDS: frozenset[str] = frozenset(
    {"metric", "op", "threshold", "severity", "enabled", "note", "actions"}
)
_OPERATORS = frozenset({">", ">=", "<", "<=", "=", "!="})
_SEVERITIES = frozenset({"info", "warn", "critical"})
_MAX_NOTE = 200


def update_rule(
    rule: MetricRule, changes: dict[str, object]
) -> tuple[MetricRule, tuple[DomainEvent, ...]]:
    unknown = set(changes) - PATCHABLE_FIELDS
    if unknown:
        raise InvalidStateError(f"不允许修改字段：{', '.join(sorted(unknown))}")
    values: dict[str, object] = {}
    if "metric" in changes:
        values["metric"] = _text(changes["metric"], "指标 id", 64)
    if "op" in changes:
        op = _text(changes["op"], "操作符", 2)
        if op not in _OPERATORS:
            raise InvalidStateError("操作符只支持 > >= < <= = !=")
        values["op"] = op
    if "threshold" in changes:
        values["threshold"] = _number(changes["threshold"])
    if "severity" in changes:
        severity = _text(changes["severity"], "级别", 16)
        if severity not in _SEVERITIES:
            raise InvalidStateError("级别只支持 info / warn / critical")
        values["severity"] = severity
    if "enabled" in changes:
        values["enabled"] = bool(changes["enabled"])
    if "note" in changes:
        values["note"] = _text(changes["note"], "说明", _MAX_NOTE, allow_empty=True)
    if "actions" in changes:
        values["actions"] = _actions(changes["actions"])
    if all(getattr(rule, key) == value for key, value in values.items()):
        return rule, ()
    updated = replace(rule, **values)
    event = DomainEvent(
        kind="metrics.rule_updated",
        payload={"rule_id": rule.rule_id, "fields": sorted(values)},
    )
    return updated, (event,)


def update_layout(
    layout: MetricLayout, hidden: list[str]
) -> tuple[MetricLayout, tuple[DomainEvent, ...]]:
    if not isinstance(hidden, list) or any(not isinstance(item, str) for item in hidden):
        raise InvalidStateError("hidden 必须是字符串数组")
    values = tuple(dict.fromkeys(item.strip() for item in hidden if item.strip()))
    if values == layout.hidden:
        return layout, ()
    updated = replace(layout, hidden=values)
    event = DomainEvent(
        kind="metrics.layout_updated", payload={"hidden": list(values)}
    )
    return updated, (event,)


def _text(value: object, label: str, limit: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InvalidStateError(f"{label}必须是字符串")
    text = value.strip()
    if not text and not allow_empty:
        raise InvalidStateError(f"{label}不能为空")
    if len(text) > limit:
        raise InvalidStateError(f"{label}不能超过 {limit} 个字符")
    return text


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidStateError("阈值必须是数字")
    return float(value)


def _actions(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise InvalidStateError("actions 必须是字符串数组")
    return tuple(item.strip() for item in value if item.strip())
