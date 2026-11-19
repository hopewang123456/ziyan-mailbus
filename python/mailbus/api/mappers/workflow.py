"""workflow 协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.workflow import (
    VersionIn,
    VersionNodeOut,
    VersionOut,
    WorkflowIn,
    WorkflowOut,
)
from mailbus.application.workflow.dto import (
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


def workflow_command(payload: WorkflowIn) -> WorkflowCommand:
    return make_workflow_command(payload.name)


def version_command(payload: VersionIn) -> VersionCommand:
    return make_version_command(tuple(node.name for node in payload.nodes))
