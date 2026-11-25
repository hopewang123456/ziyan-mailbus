"""流程 Graph 命令到领域模型的转换与旧线性版本合成。"""

from __future__ import annotations

from collections.abc import Sequence

from mailbus.application.workflow.dto import (
    GraphEdgeCommand,
    GraphNodeCommand,
    ValidateIssueView,
)
from mailbus.core.shared.events import DomainEvent
from mailbus.core.workflow.models import WorkflowEdge, WorkflowNode


def nodes_of(items: Sequence[GraphNodeCommand]) -> tuple[WorkflowNode, ...]:
    return tuple(item.to_model() for item in items)


def edges_of(
    items: Sequence[GraphEdgeCommand] | None,
) -> tuple[WorkflowEdge, ...]:
    return tuple(item.to_model() for item in (items or ()))


def legacy_graph(
    nodes: Sequence[WorkflowNode],
) -> tuple[tuple[WorkflowNode, ...], tuple[WorkflowEdge, ...]]:
    """旧线性版本合成 Graph：隐式 start + 顺序链，兼容迁移前的编辑入口。"""
    start = WorkflowNode(node_id="start", name="开始", order=-1, node_type="start")
    ordered = tuple(nodes)
    chain = (start.node_id, *(node.node_id for node in ordered))
    edges = tuple(
        WorkflowEdge(from_node_id=chain[index], to_node_id=chain[index + 1])
        for index in range(len(chain) - 1)
    )
    return (start, *ordered), edges


def version_created(workflow_id: str, version: int, now) -> DomainEvent:
    return DomainEvent(
        kind="workflow.version_created",
        payload={"workflow_id": workflow_id, "version": version, "at": now.isoformat()},
    )


def issue_detail(issue: ValidateIssueView) -> dict[str, object]:
    detail: dict[str, object] = {"code": issue.code, "message_zh": issue.message_zh}
    if issue.node_id is not None:
        detail["node_id"] = issue.node_id
    if issue.edge is not None:
        detail["edge"] = {
            "from_node_id": issue.edge[0],
            "to_node_id": issue.edge[1],
        }
    return detail
