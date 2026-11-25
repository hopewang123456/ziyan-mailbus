"""任务图索引（纯结构，不做条件解释）。"""

from __future__ import annotations

from mailbus.core.workflow.models import WorkflowEdge, WorkflowNode


class GraphIndex:
    """一次执行内复用的只读索引；回边 = 指向更早节点的边。"""

    def __init__(self, nodes: list[WorkflowNode], edges: list[WorkflowEdge]) -> None:
        self.nodes = {node.node_id: node for node in nodes}
        self.outgoing: dict[str, list[WorkflowEdge]] = {node.node_id: [] for node in nodes}
        self.incoming: dict[str, list[WorkflowEdge]] = {node.node_id: [] for node in nodes}
        for edge in edges:
            self.outgoing.setdefault(edge.from_node_id, []).append(edge)
            self.incoming.setdefault(edge.to_node_id, []).append(edge)

    def node(self, node_id: str) -> WorkflowNode | None:
        return self.nodes.get(node_id)

    def is_back_edge(self, edge: WorkflowEdge) -> bool:
        source = self.nodes.get(edge.from_node_id)
        target = self.nodes.get(edge.to_node_id)
        if source is None or target is None:
            return False
        return target.order < source.order

    def forward_edges(self, node_id: str) -> list[WorkflowEdge]:
        return [edge for edge in self.outgoing.get(node_id, []) if not self.is_back_edge(edge)]

    def back_edges(self, node_id: str) -> list[WorkflowEdge]:
        return [edge for edge in self.outgoing.get(node_id, []) if self.is_back_edge(edge)]

    def predecessors(self, node_id: str) -> list[str]:
        found: list[str] = []
        for edge in self.incoming.get(node_id, []):
            if self.is_back_edge(edge):
                continue
            if edge.from_node_id not in found:
                found.append(edge.from_node_id)
        return found

    def start_nodes(self) -> list[str]:
        """无前向入边的节点；正常图应为唯一的 start。"""
        return [
            node_id
            for node_id in self.nodes
            if not self.predecessors(node_id) and node_id in self.outgoing
        ]

    def ordered(self) -> list[WorkflowNode]:
        return sorted(self.nodes.values(), key=lambda node: node.order)
