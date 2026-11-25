"""workflow 协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.contract.workflow import (
    EdgeRefOut,
    GraphEdgeIn,
    GraphIn,
    GraphNodeIn,
    GraphOut,
    ValidateIssueOut,
    ValidateOut,
    VersionOut as ContractVersionOut,
    WorkflowGraphIn,
    WorkflowOut as ContractWorkflowOut,
)
from mailbus.api.schemas.workflow import (
    VersionIn,
    VersionNodeOut,
    VersionOut,
    WorkflowIn,
    WorkflowOut,
)
from mailbus.application.workflow.dto import (
    GraphEdgeCommand,
    GraphNodeCommand,
    GraphView,
    ValidateIssueView,
    ValidateView,
    VersionCommand,
    VersionView,
    WorkflowCommand,
    WorkflowView,
    make_version_command,
    make_workflow_command,
)


def to_workflow_out(view: WorkflowView) -> WorkflowOut:
    return WorkflowOut(
        workflow_id=view.workflow_id,
        name=view.name,
        latest_version=view.latest_version,
        published_version=view.published_version,
        created_at=view.created_at,
    )


def to_contract_workflow_out(view: WorkflowView) -> ContractWorkflowOut:
    return ContractWorkflowOut(
        workflow_id=view.workflow_id,
        name=view.name,
        latest_version=view.latest_version,
        published_version=view.published_version,
        created_at=view.created_at,
    )


def to_version_out(view: VersionView) -> VersionOut:
    return VersionOut(
        workflow_id=view.workflow_id,
        version=view.version,
        state=view.state,
        nodes=[
            VersionNodeOut(node_id=node.node_id, name=node.name, order=node.order)
            for node in view.nodes
        ],
        created_at=view.created_at,
        published_at=view.published_at,
    )


def to_contract_version_out(view: VersionView) -> ContractVersionOut:
    return ContractVersionOut(
        workflow_id=view.workflow_id,
        version=view.version,
        state=view.state,
        revision=view.revision,
        created_at=view.created_at,
        published_at=view.published_at,
    )


def workflow_command(payload: WorkflowIn) -> WorkflowCommand:
    return make_workflow_command(payload.name)


def version_command(payload: VersionIn) -> VersionCommand:
    return make_version_command(tuple(node.name for node in payload.nodes))


def to_graph_out(view: GraphView) -> GraphOut:
    return GraphOut(
        graph=WorkflowGraphIn(
            nodes=[
                GraphNodeIn(
                    node_id=node.node_id,
                    name=node.name,
                    node_type=node.node_type,  # type: ignore[arg-type]
                    position_id=node.position_id,
                    seq=node.seq,
                    prompt_template=node.prompt_template,
                    needs_artifacts_from=list(node.needs_artifacts_from),
                    max_retries=node.max_retries,
                    max_loops=node.max_loops,
                    timeout_seconds=node.timeout_seconds,
                    config=node.config,
                    pos_x=node.pos_x,
                    pos_y=node.pos_y,
                )
                for node in view.nodes
            ],
            edges=[
                GraphEdgeIn(
                    from_node_id=edge.from_node_id,
                    to_node_id=edge.to_node_id,
                    condition=edge.condition,
                )
                for edge in view.edges
            ],
        ),
        revision=view.revision,
    )


def graph_nodes(payload: WorkflowGraphIn) -> tuple[GraphNodeCommand, ...]:
    return tuple(
        GraphNodeCommand(
            node_id=node.node_id,
            name=node.name,
            node_type=node.node_type,
            position_id=node.position_id,
            seq=node.seq,
            prompt_template=node.prompt_template,
            needs_artifacts_from=tuple(node.needs_artifacts_from),
            max_retries=node.max_retries,
            max_loops=node.max_loops,
            timeout_seconds=node.timeout_seconds,
            config=dict(node.config or {}),
            pos_x=node.pos_x,
            pos_y=node.pos_y,
        )
        for node in payload.nodes
    )


def graph_edges(payload: WorkflowGraphIn) -> tuple[GraphEdgeCommand, ...]:
    return tuple(
        GraphEdgeCommand(
            from_node_id=edge.from_node_id,
            to_node_id=edge.to_node_id,
            condition=edge.condition,
        )
        for edge in payload.edges
    )


def to_validate_out(view: ValidateView) -> ValidateOut:
    return ValidateOut(
        ok=view.ok,
        errors=[_issue_out(item) for item in view.errors],
        warnings=[_issue_out(item) for item in view.warnings],
        stats=view.stats,
    )


def _issue_out(item: ValidateIssueView) -> ValidateIssueOut:
    return ValidateIssueOut(
        code=item.code,
        message_zh=item.message_zh,
        node_id=item.node_id,
        edge=None
        if item.edge is None
        else EdgeRefOut(from_node_id=item.edge[0], to_node_id=item.edge[1]),
    )


def graph_in(payload: GraphIn) -> tuple[tuple[WorkflowNode, ...], tuple[WorkflowEdge, ...]]:
    return graph_nodes(payload.graph), graph_edges(payload.graph)
