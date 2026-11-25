"""校验结果模型与保存前结构校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from mailbus.core.workflow.models import WorkflowEdge, WorkflowNode

NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    message_zh: str
    node_id: str | None = None
    edge: WorkflowEdge | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    errors: tuple[Issue, ...] = ()
    warnings: tuple[Issue, ...] = ()
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def structural_issues(
    nodes: tuple[WorkflowNode, ...], edges: tuple[WorkflowEdge, ...]
) -> tuple[Issue, ...]:
    """仅 4 类结构性错误：PUT 时阻断保存。"""
    issues: list[Issue] = []
    seen: set[str] = set()
    for node in nodes:
        if not NODE_ID_PATTERN.match(node.node_id):
            issues.append(
                Issue("E_INVALID_NODE_ID", f"节点 ID「{node.node_id}」不合法", node.node_id)
            )
        if node.node_id in seen:
            issues.append(
                Issue("E_DUPLICATE_NODE_ID", f"节点 ID「{node.node_id}」重复", node.node_id)
            )
        seen.add(node.node_id)
    known = {node.node_id for node in nodes}
    for edge in edges:
        if edge.from_node_id not in known or edge.to_node_id not in known:
            issues.append(_dangling(edge))
            continue
        if edge.condition and not parsable(edge.condition):
            issues.append(
                Issue(
                    "E_CONDITION_SYNTAX",
                    f"连线 {edge.from_node_id} → {edge.to_node_id} 的条件不是合法 JSON",
                    edge=edge,
                )
            )
    return tuple(issues)


def _dangling(edge: WorkflowEdge) -> Issue:
    return Issue(
        "E_DANGLING_EDGE",
        f"连线 {edge.from_node_id} → {edge.to_node_id} 指向不存在的节点",
        edge=edge,
    )


def parsable(value: str) -> bool:
    try:
        json.loads(value)
    except (TypeError, ValueError):
        return False
    return True
