"""发布前语义校验：六类节点、开始/终验、显式汇聚、扇出与条件。"""

from __future__ import annotations

import re

from mailbus.application.workflow.validation import graph as g
from mailbus.application.workflow.validation.conditions import condition_issues
from mailbus.application.workflow.validation.issues import (
    Issue,
    ValidationReport,
    structural_issues,
)
from mailbus.core.workflow.models import WorkflowEdge, WorkflowNode

_PROMPT_VAR = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_PROMPT_PREFIXES = ("task.", "workflow.", "node.", "role.")
_CRON_PATTERN = re.compile(r"[0-9A-Za-z*/,?\-]+")


def validate(
    nodes: tuple[WorkflowNode, ...], edges: tuple[WorkflowEdge, ...]
) -> ValidationReport:
    errors: list[Issue] = list(structural_issues(nodes, edges))
    warnings: list[Issue] = []
    node_map = {node.node_id: node for node in nodes}
    usable = [
        edge
        for edge in edges
        if edge.from_node_id in node_map and edge.to_node_id in node_map
    ]
    graph = g.adjacency(node_map, usable)
    back_edges = {id(edge) for edge in usable if g.is_back_edge(edge, graph)}
    starts = [node for node in nodes if node.node_type == "start"]
    finals = [node for node in nodes if node.node_type == "final_approval"]

    _check_endpoints(errors, starts, finals)
    for node in nodes:
        _check_node(node, errors, warnings)
    for edge in usable:
        _check_edge(edge, node_map, starts, errors)
    _check_finals(finals, usable, back_edges, errors)
    _check_indegree(node_map, usable, back_edges, errors)
    for node in nodes:
        _check_out_edges(node, graph, errors)
    _check_orphans(nodes, starts, graph, errors)
    _check_cycles(node_map, usable, errors)

    return ValidationReport(
        errors=tuple(errors),
        warnings=tuple(warnings),
        stats={
            "node_count": len(nodes),
            "edge_count": len(edges),
            "max_depth": g.max_depth(starts[0].node_id, graph) if starts else 0,
            "has_cycle": g.has_cycle(graph),
        },
    )


def _check_endpoints(
    errors: list[Issue], starts: list[WorkflowNode], finals: list[WorkflowNode]
) -> None:
    if not starts:
        errors.append(Issue("E_MISSING_START", "缺少开始节点"))
    elif len(starts) > 1:
        for node in starts:
            errors.append(Issue("E_MULTI_START", "开始节点只能有一个", node.node_id))
    if not finals:
        errors.append(Issue("E_NO_FINAL", "缺少终验节点"))


def _check_node(
    node: WorkflowNode, errors: list[Issue], warnings: list[Issue]
) -> None:
    if node.node_type in {"agent", "human", "final_approval"} and not (
        node.position_id or _assignee(node)
    ):
        errors.append(
            Issue("E_NO_POSITION", f"节点「{node.name}」未绑定岗位", node.node_id)
        )
    prompt = (node.prompt_template or "").strip()
    if node.node_type == "agent" and not prompt:
        warnings.append(Issue("W_NO_PROMPT", f"节点「{node.name}」没有指令模板", node.node_id))
    if node.node_type == "human" and not prompt:
        warnings.append(
            Issue("W_HUMAN_NO_PROMPT", f"节点「{node.name}」没有任务说明", node.node_id)
        )
    unknown = _unknown_vars(node.prompt_template)
    if unknown:
        warnings.append(
            Issue(
                "W_PROMPT_UNKNOWN_VAR",
                f"节点「{node.name}」模板含未知变量：{', '.join(unknown)}",
                node.node_id,
            )
        )
    _check_fanout(node, errors, warnings)
    if node.timeout_seconds and node.timeout_seconds > 7 * 24 * 3600:
        warnings.append(
            Issue("W_LONG_TIMEOUT", f"节点「{node.name}」超时超过 7 天", node.node_id)
        )
    if node.node_type == "start":
        issue = _trigger_issue(node)
        if issue is not None:
            errors.append(issue)


def _check_fanout(
    node: WorkflowNode, errors: list[Issue], warnings: list[Issue]
) -> None:
    size = _fanout_size(node)
    if size is None:
        return
    if size not in range(2, 11):
        errors.append(
            Issue("E_FANOUT_INVALID", f"节点「{node.name}」扇出人数必须在 2–10 之间", node.node_id)
        )
    elif size > 5:
        warnings.append(
            Issue("W_HIGH_FANOUT", f"节点「{node.name}」扇出人数超过 5", node.node_id)
        )


def _check_edge(
    edge: WorkflowEdge,
    node_map: dict[str, WorkflowNode],
    starts: list[WorkflowNode],
    errors: list[Issue],
) -> None:
    if edge.from_node_id == edge.to_node_id:
        errors.append(
            Issue(
                "E_SELF_LOOP",
                f"节点「{node_map[edge.from_node_id].name}」不能连到自己",
                edge.from_node_id,
                edge,
            )
        )
    if any(edge.to_node_id == node.node_id for node in starts):
        errors.append(
            Issue("E_START_INBOUND", "开始节点不能有入边", edge.to_node_id, edge)
        )
    if edge.condition:
        errors.extend(condition_issues(edge, node_map.get(edge.from_node_id)))


def _check_finals(
    finals: list[WorkflowNode],
    edges: list[WorkflowEdge],
    back_edges: set[int],
    errors: list[Issue],
) -> None:
    for edge in edges:
        source = next(
            (node for node in finals if node.node_id == edge.from_node_id), None
        )
        if source is not None and id(edge) not in back_edges:
            errors.append(
                Issue(
                    "E_FINAL_FORWARD",
                    f"终验节点「{source.name}」的出边只能是打回",
                    source.node_id,
                    edge,
                )
            )
    for final in finals:
        rework = [
            edge
            for edge in edges
            if edge.from_node_id == final.node_id and id(edge) in back_edges
        ]
        for edge in rework[1:]:
            errors.append(
                Issue(
                    "E_FINAL_REWORK_EDGES",
                    f"终验节点「{final.name}」最多只能有一条回边",
                    final.node_id,
                    edge,
                )
            )


def _check_indegree(
    node_map: dict[str, WorkflowNode],
    edges: list[WorkflowEdge],
    back_edges: set[int],
    errors: list[Issue],
) -> None:
    counts: dict[str, int] = {node_id: 0 for node_id in node_map}
    for edge in edges:
        if id(edge) not in back_edges:
            counts[edge.to_node_id] = counts.get(edge.to_node_id, 0) + 1
    for node in node_map.values():
        if node.node_type in {"start", "parallel_join"}:
            continue
        if counts[node.node_id] > 1:
            errors.append(
                Issue(
                    "E_MULTI_IN_REQUIRES_JOIN",
                    f"节点「{node.name}」有多条前向入边，请先插入汇聚节点",
                    node.node_id,
                )
            )


def _check_out_edges(
    node: WorkflowNode,
    graph: dict[str, list[WorkflowEdge]],
    errors: list[Issue],
) -> None:
    out_edges = graph.get(node.node_id, [])
    if len(out_edges) >= 2:
        flags = [bool(edge.condition) for edge in out_edges]
        if any(flags) and not all(flags):
            errors.append(
                Issue("E_MIXED_OUT_EDGES", f"节点「{node.name}」的出边条件不一致", node.node_id)
            )
        if _fanout_size(node) is not None:
            errors.append(
                Issue(
                    "E_FANOUT_WITH_MULTI_OUT",
                    f"节点「{node.name}」开启扇出时只能有一条出边",
                    node.node_id,
                )
            )


def _check_orphans(
    nodes: tuple[WorkflowNode, ...],
    starts: list[WorkflowNode],
    graph: dict[str, list[WorkflowEdge]],
    errors: list[Issue],
) -> None:
    if not starts:
        return
    reached = g.reachable(starts[0].node_id, graph)
    for node in nodes:
        if node.node_id not in reached:
            errors.append(
                Issue("E_ORPHAN_NODE", f"节点「{node.name}」无法从开始节点到达", node.node_id)
            )


def _check_cycles(
    node_map: dict[str, WorkflowNode],
    edges: list[WorkflowEdge],
    errors: list[Issue],
) -> None:
    for component in g.strong_components(node_map, edges):
        internal = [
            edge
            for edge in edges
            if edge.from_node_id in component and edge.to_node_id in component
        ]
        if len(component) == 1 and not internal:
            continue
        if any(edge.condition for edge in internal):
            continue
        for node_id in component:
            node = node_map[node_id]
            if node.max_loops == 0:
                errors.append(
                    Issue(
                        "E_CYCLE_UNCONDITIONAL",
                        f"节点「{node.name}」所在环没有条件边且循环上限为 0",
                        node_id,
                    )
                )


def _assignee(node: WorkflowNode) -> str | None:
    value = node.config.get("assignee_id") if isinstance(node.config, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def _fanout_size(node: WorkflowNode) -> int | None:
    if not isinstance(node.config, dict):
        return None
    fanout = node.config.get("fanout")
    if not isinstance(fanout, dict) or not fanout.get("enabled"):
        return None
    size = fanout.get("size")
    return size if isinstance(size, int) and not isinstance(size, bool) else -1


def _unknown_vars(template: str | None) -> list[str]:
    if not template:
        return []
    unknown: list[str] = []
    for name in _PROMPT_VAR.findall(template):
        plain = name.strip()
        if plain == "artifacts" or plain.startswith("artifacts."):
            continue
        if plain.startswith(_PROMPT_PREFIXES):
            continue
        if plain not in unknown:
            unknown.append(plain)
    return unknown


def _trigger_issue(node: WorkflowNode) -> Issue | None:
    trigger = node.config.get("trigger") if isinstance(node.config, dict) else None
    if not isinstance(trigger, dict):
        return None
    modes = trigger.get("mode")
    modes = modes if isinstance(modes, list) else []
    if not ({"schedule", "cron"} & {str(mode) for mode in modes}):
        return None
    cron = trigger.get("cron")
    if not isinstance(cron, str) or not _valid_cron(cron):
        return Issue(
            "E_TRIGGER_CRON",
            f"开始节点「{node.name}」启用定时触发但 cron 为空或非法",
            node.node_id,
        )
    return None


def _valid_cron(value: str) -> bool:
    parts: list[str] = value.split()
    if len(parts) != 5:
        return False
    return all(_CRON_PATTERN.fullmatch(part) for part in parts)


__all__: list[str] = ["validate"]
