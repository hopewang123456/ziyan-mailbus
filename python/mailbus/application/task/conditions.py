"""条件规则求值：有副作用的白名单解释放在应用层。

core 只保留图结构；规则 JSON 的解析与比较属于用例策略。
"""

from __future__ import annotations

import json
import re
from typing import Any

_FIELD_PREFIXES = ("result.", "task.", "node.", "context.", "artifacts.")


def parse_result(text: str | None) -> Any:
    """result 以 TEXT 保存；能解析为 JSON 就按 JSON，否则按原文。"""
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def is_failed_result(text: str | None) -> bool:
    """结果是带 status 的 JSON 且 status=failed/rejected 时按失败推进。"""
    parsed = parse_result(text)
    if not isinstance(parsed, dict):
        return False
    return str(parsed.get("status", "")).lower() in {"failed", "rejected"}


def evaluate(condition: str | None, context: dict[str, Any]) -> bool:
    """无条件的边恒成立；非法条件一律视为不命中（发布阶段已校验）。"""
    if not condition:
        return True
    try:
        rule = json.loads(condition)
    except (TypeError, ValueError):
        return False
    return _match(rule, context)


def _match(rule: Any, context: dict[str, Any]) -> bool:
    if not isinstance(rule, dict):
        return False
    if "and" in rule:
        return all(_match(item, context) for item in rule["and"])
    if "or" in rule:
        return any(_match(item, context) for item in rule["or"])
    name = rule.get("field")
    if not isinstance(name, str) or not name.startswith(_FIELD_PREFIXES):
        return False
    return _compare(_resolve(name, context), str(rule.get("op")), rule.get("value"))


def _resolve(name: str, context: dict[str, Any]) -> Any:
    head, _, tail = name.partition(".")
    value: Any = context.get(head)
    for part in tail.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _compare(left: Any, op: str, right: Any) -> bool:
    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op in {">", ">=", "<", "<="}:
            return _ordered(left, right, op)
        if op == "contains":
            return left is not None and right in left
        if op == "in":
            return left in right if isinstance(right, list) else False
        if op == "not_in":
            return left not in right if isinstance(right, list) else False
        if op == "startsWith":
            return isinstance(left, str) and left.startswith(str(right))
        if op == "endsWith":
            return isinstance(left, str) and left.endswith(str(right))
        if op == "regex":
            return isinstance(left, str) and re.search(str(right), left) is not None
    except (TypeError, ValueError, re.error):
        return False
    return False


def _ordered(left: Any, right: Any, op: str) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    return left <= right
