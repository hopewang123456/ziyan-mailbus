"""图结构算法：邻接、后向边、可达、环与最长深度。"""

from __future__ import annotations

from collections import deque

from mailbus.core.workflow.models import WorkflowEdge, WorkflowNode


def adjacency(
    nodes: dict[str, WorkflowNode], edges: list[WorkflowEdge]
) -> dict[str, list[WorkflowEdge]]:
    result: dict[str, list[WorkflowEdge]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        result[edge.from_node_id].append(edge)
    return result


def is_back_edge(
    edge: WorkflowEdge, graph: dict[str, list[WorkflowEdge]]
) -> bool:
    """目标能反向到达源，即这条边闭合了一个环（打回边）。"""
    if edge.from_node_id == edge.to_node_id:
        return True
    seen = {edge.to_node_id}
    queue = deque([edge.to_node_id])
    while queue:
        current = queue.popleft()
        for item in graph.get(current, []):
            if item.to_node_id == edge.from_node_id:
                return True
            if item.to_node_id not in seen:
                seen.add(item.to_node_id)
                queue.append(item.to_node_id)
    return False


def reachable(start: str, graph: dict[str, list[WorkflowEdge]]) -> set[str]:
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for edge in graph.get(current, []):
            if edge.to_node_id not in seen:
                seen.add(edge.to_node_id)
                queue.append(edge.to_node_id)
    return seen


def has_cycle(graph: dict[str, list[WorkflowEdge]]) -> bool:
    visiting: set[str] = set()
    done: set[str] = set()

    def walk(node_id: str, path: set[str]) -> bool:
        if node_id in path:
            return True
        if node_id in done:
            return False
        path.add(node_id)
        for edge in graph.get(node_id, []):
            if walk(edge.to_node_id, path):
                return True
        path.discard(node_id)
        done.add(node_id)
        return False

    return any(walk(node_id, set()) for node_id in graph)


def strong_components(
    nodes: dict[str, WorkflowNode], edges: list[WorkflowEdge]
) -> list[set[str]]:
    links: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        links[edge.from_node_id].append(edge.to_node_id)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[set[str]] = []
    counter = 0

    def visit(node_id: str) -> None:
        nonlocal counter
        index[node_id] = low[node_id] = counter
        counter += 1
        stack.append(node_id)
        on_stack.add(node_id)
        for target in links.get(node_id, []):
            if target not in index:
                visit(target)
                low[node_id] = min(low[node_id], low[target])
            elif target in on_stack:
                low[node_id] = min(low[node_id], index[target])
        if low[node_id] != index[node_id]:
            return
        component: set[str] = set()
        while True:
            current = stack.pop()
            on_stack.discard(current)
            component.add(current)
            if current == node_id:
                break
        result.append(component)

    for node_id in links:
        if node_id not in index:
            visit(node_id)
    return result


def max_depth(start: str, graph: dict[str, list[WorkflowEdge]]) -> int:
    """只沿前向边计算最长路径；回边不参与。"""
    memo: dict[str, int] = {}

    def depth(node_id: str, path: frozenset[str]) -> int:
        if node_id in memo:
            return memo[node_id]
        best = 1
        for edge in graph.get(node_id, []):
            if edge.to_node_id in path:
                continue
            best = max(best, depth(edge.to_node_id, path | {edge.to_node_id}) + 1)
        memo[node_id] = best
        return best

    return depth(start, frozenset({start}))
