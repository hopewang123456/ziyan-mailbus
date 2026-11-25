"""条件 JSON 的白名单校验。"""

from __future__ import annotations

import json
import re
from typing import Any

from mailbus.application.workflow.validation.issues import Issue
from mailbus.core.workflow.models import WorkflowEdge, WorkflowNode

_NUMERIC_OPS = frozenset({">=", "<=", ">", "<"})
_VALID_OPS = frozenset(
    {
        "==",
        "!=",
        ">=",
        "<=",
        ">",
        "<",
        "contains",
        "in",
        "not_in",
        "startsWith",
        "endsWith",
        "regex",
    }
)
_FIELD_PREFIXES = ("result.", "task.", "node.", "context.", "artifacts.")


def condition_issues(edge: WorkflowEdge, source: WorkflowNode | None) -> list[Issue]:
    try:
        parsed = json.loads(edge.condition or "")
    except (TypeError, ValueError):
        return []
    return _check_node(parsed, edge, source)


def _check_node(
    node: Any, edge: WorkflowEdge, source: WorkflowNode | None
) -> list[Issue]:
    where = f"连线 {edge.from_node_id} → {edge.to_node_id} 的条件"
    node_id = source.node_id if source else None
    if not isinstance(node, dict):
        return [_syntax(where, node_id, edge)]
    if "and" in node or "or" in node:
        return _check_group(node, where, node_id, edge, source)
    return _check_rule(node, where, node_id, edge)


def _check_group(node, where, node_id, edge, source) -> list[Issue]:
    items = node.get("and") if "and" in node else node.get("or")
    if not isinstance(items, list):
        return [_syntax(where, node_id, edge)]
    if not items:
        return [Issue("E_CONDITION_EMPTY_GROUP", f"{where}分组为空", node_id, edge)]
    issues: list[Issue] = []
    for item in items:
        issues.extend(_check_node(item, edge, source))
    return issues


def _check_rule(node, where, node_id, edge) -> list[Issue]:
    issues: list[Issue] = []
    name = node.get("field")
    if not isinstance(name, str) or not name.startswith(_FIELD_PREFIXES):
        issues.append(Issue("E_CONDITION_FIELD", f"{where}的字段不在白名单", node_id, edge))
    op = node.get("op")
    if op not in _VALID_OPS:
        issues.append(Issue("E_CONDITION_OP", f"{where}的运算符不合法", node_id, edge))
    issues.extend(_value_issues(op, node.get("value"), where, node_id, edge))
    return issues


def _value_issues(op, value, where, node_id, edge) -> list[Issue]:
    if op in {"in", "not_in"} and not isinstance(value, list):
        return [Issue("E_CONDITION_VALUE", f"{where}的 in 值必须是数组", node_id, edge)]
    if op == "regex":
        return _regex_issues(value, where, node_id, edge)
    if op in _NUMERIC_OPS and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        return [Issue("E_CONDITION_VALUE", f"{where}的数值比较缺少数字", node_id, edge)]
    return []


def _regex_issues(value, where, node_id, edge) -> list[Issue]:
    if not isinstance(value, str):
        return [Issue("E_CONDITION_VALUE", f"{where}的 regex 必须是字符串", node_id, edge)]
    try:
        re.compile(value)
    except re.error:
        return [Issue("E_CONDITION_VALUE", f"{where}的 regex 非法", node_id, edge)]
    return []


def _syntax(where, node_id, edge) -> Issue:
    return Issue("E_CONDITION_SYNTAX", f"{where}结构不合法", node_id, edge)
