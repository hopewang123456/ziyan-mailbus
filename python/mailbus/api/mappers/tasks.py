"""task 协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.tasks import (
    PublicTaskNodeOut,
    PublicTaskOut,
    TaskIn,
    TaskNodeOut,
    TaskOut,
)
from mailbus.application.workflow.dto import TaskCommand, TaskView, make_task_command


def to_task_out(view: TaskView) -> TaskOut:
    return TaskOut(
        task_id=view.task_id,
        title=view.title,
        state=view.state,
        workflow_id=view.workflow_id,
        workflow_version=view.workflow_version,
        owner_id=view.owner_id,
        created_by=view.created_by,
        created_at=view.created_at,
        updated_at=view.updated_at,
        nodes=[
            TaskNodeOut(
                node_id=node.node_id,
                name=node.name,
                order=node.order,
                state=node.state,
            )
            for node in view.nodes
        ],
    )


def to_public_task_out(view: TaskView) -> PublicTaskOut:
    return PublicTaskOut(
        task_id=view.task_id,
        title=view.title,
        state=view.state,
        created_at=view.created_at,
        updated_at=view.updated_at,
        nodes=[
            PublicTaskNodeOut(name=node.name, order=node.order, state=node.state)
            for node in view.nodes
        ],
    )


def task_command(payload: TaskIn) -> TaskCommand:
    return make_task_command(
        title=payload.title,
        owner_id=payload.owner_id,
        workflow_id=payload.workflow_id,
        workflow_version=payload.workflow_version,
    )
