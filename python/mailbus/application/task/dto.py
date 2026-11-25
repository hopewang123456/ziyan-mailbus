"""任务用例的输入与读出模型（不含 pydantic，api 层再转契约 DTO）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mailbus.core.approval.values import ApprovalStatus
from mailbus.core.shared.errors import InvalidStateError
from mailbus.core.workflow.models import Task, TaskArtifact, TaskNode, TaskRun
from mailbus.core.workflow.values import NodeState, RunState


def parse_approval_state(state: str | None) -> ApprovalStatus | None:
    if state is None:
        return None
    try:
        return ApprovalStatus(state)
    except ValueError as exc:
        raise InvalidStateError(f"未知审批状态：{state}") from exc

OPEN_TASK_STATES = frozenset({"pending", "running", "blocked"})
ACTIVE_NODE_STATES = ("running", "dispatched", "waiting_human", "blocked")


@dataclass(frozen=True, slots=True)
class CreateTaskCommand:
    title: str
    workflow_id: str | None = None
    owner_id: str | None = None
    variables: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubmitResultCommand:
    attempt_no: int
    result: str
    artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RerunJoinCommand:
    fanout_group: str
    scope: str = "join"


@dataclass(frozen=True, slots=True)
class TaskRunView:
    run_id: str
    node_id: str
    attempt_no: int
    fanout_slot: int
    state: str
    assigned_employee_id: str | None
    fanout_group: str | None
    dispatched_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    result: str | None


@dataclass(frozen=True, slots=True)
class TaskNodeView:
    node_id: str
    name: str
    seq: int
    state: str
    current_run_id: str | None
    runs: tuple[TaskRunView, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskDetailView:
    task: Task
    nodes: tuple[TaskNodeView, ...]
    runs: tuple[TaskRunView, ...]
    variables: dict[str, str] = field(default_factory=dict)
    artifacts: tuple["ArtifactView", ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactView:
    artifact_id: str
    task_id: str
    node_id: str | None
    run_id: str | None
    file_name: str
    artifact_type: str | None
    description: str | None
    size_bytes: int | None
    created_by: str | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class TaskSummaryView:
    task: Task
    current_node: str | None
    progress_done: int
    progress_total: int
    claimable: bool


@dataclass(frozen=True, slots=True)
class TaskCountersView:
    claimable: int
    mine_open: int
    approvals: int


def run_view(run: TaskRun) -> TaskRunView:
    return TaskRunView(
        run_id=run.run_id,
        node_id=run.node_id,
        attempt_no=run.attempt_no,
        fanout_slot=run.fanout_slot,
        state=run.state.value,
        assigned_employee_id=run.assigned_employee_id,
        fanout_group=run.fanout_group,
        dispatched_at=run.dispatched_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        result=run.result,
    )


def artifact_view(artifact: TaskArtifact) -> ArtifactView:
    size: int | None = None
    try:
        size = Path(artifact.file_path).stat().st_size
    except OSError:
        size = None
    return ArtifactView(
        artifact_id=artifact.artifact_id,
        task_id=artifact.task_id,
        node_id=artifact.node_id,
        run_id=artifact.run_id,
        file_name=artifact.file_name,
        artifact_type=artifact.artifact_type,
        description=artifact.description,
        size_bytes=size,
        created_by=artifact.created_by,
        created_at=artifact.created_at,
    )


def node_views(nodes: list[TaskNode], runs: list[TaskRun]) -> tuple[TaskNodeView, ...]:
    grouped: dict[str, list[TaskRunView]] = {}
    for run in runs:
        grouped.setdefault(run.node_id, []).append(run_view(run))
    return tuple(
        TaskNodeView(
            node_id=node.node_id,
            name=node.name,
            seq=node.order,
            state=node.state.value,
            current_run_id=node.current_run_id,
            runs=tuple(grouped.get(node.node_id, ())),
        )
        for node in nodes
    )


def summary_view(
    task: Task, nodes: list[TaskNode], runs: list[TaskRun], claimable_ids: set[str]
) -> TaskSummaryView:
    current = _current_node(nodes)
    done = sum(1 for node in nodes if node.state is NodeState.DONE)
    claimable = any(
        run.state is RunState.WAITING_HUMAN
        and run.assigned_employee_id is None
        and run.node_id in claimable_ids
        for run in runs
    )
    return TaskSummaryView(
        task=task,
        current_node=current.name if current else None,
        progress_done=done,
        progress_total=len(nodes),
        claimable=claimable,
    )


def _current_node(nodes: list[TaskNode]) -> TaskNode | None:
    for state in ACTIVE_NODE_STATES:
        for node in nodes:
            if node.state.value == state:
                return node
    for node in nodes:
        if node.state is NodeState.PENDING:
            return node
    return nodes[-1] if nodes else None
