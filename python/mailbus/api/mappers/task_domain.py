"""任务域 wire 映射：application 视图 → 冻结契约 DTO。"""

from __future__ import annotations

from mailbus.api.schemas.contract.task import (
    ArtifactOut,
    TaskCountersOut,
    TaskDetailOut,
    TaskListOut,
    TaskNodeOut,
    TaskRunOut,
    TaskSummaryOut,
    TaskTraceEventOut,
    TaskTraceOut,
)
from mailbus.application.task.dto import (
    ArtifactView,
    TaskCountersView,
    TaskDetailView,
    TaskNodeView,
    TaskRunView,
    TaskSummaryView,
)

# 内部执行态只在契约既有取值内投影，不新增 wire 枚举。
_RUN_STATE = {
    "pending": "pending",
    "dispatched": "running",
    "running": "running",
    "waiting_human": "pending",
    "done": "done",
    "failed": "failed",
    "skipped": "skipped",
}


def to_run_out(run: TaskRunView) -> TaskRunOut:
    return TaskRunOut(
        run_id=run.run_id,
        node_id=run.node_id,
        attempt_no=run.attempt_no,
        fanout_slot=run.fanout_slot,
        state=_RUN_STATE.get(run.state, run.state),
        assigned_employee_id=run.assigned_employee_id,
        fanout_group=run.fanout_group,
        dispatched_at=run.dispatched_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        result=run.result,
    )


def to_node_out(node: TaskNodeView) -> TaskNodeOut:
    return TaskNodeOut(
        node_id=node.node_id,
        name=node.name,
        seq=node.seq,
        state=node.state,
        current_run_id=node.current_run_id,
        runs=[to_run_out(run) for run in node.runs],
    )


def to_artifact(view: ArtifactView) -> ArtifactOut:
    return ArtifactOut(
        artifact_id=view.artifact_id,
        task_id=view.task_id,
        node_id=view.node_id,
        run_id=view.run_id,
        file_name=view.file_name,
        artifact_type=view.artifact_type,
        description=view.description,
        size_bytes=view.size_bytes,
        created_by=view.created_by,
        created_at=view.created_at,
    )


def to_detail(view: TaskDetailView) -> TaskDetailOut:
    task = view.task
    return TaskDetailOut(
        task_id=task.task_id,
        title=task.title,
        state=task.state.value,
        owner_id=task.owner_id,
        created_by=task.created_by,
        workflow_id=task.workflow_id,
        workflow_version=task.workflow_version,
        termination_reason=task.termination_reason,
        created_at=task.created_at,
        updated_at=task.updated_at,
        nodes=[to_node_out(node) for node in view.nodes],
        runs=[to_run_out(run) for run in view.runs],
        artifacts=[to_artifact(item) for item in view.artifacts],
    )


def to_trace(view: TaskDetailView) -> TaskTraceOut:
    task = view.task
    events = [TaskTraceEventOut(
        at=task.created_at,
        kind="task.created",
        detail={"title": task.title, "state": task.state.value},
    )]
    for run in view.runs:
        state = _RUN_STATE.get(run.state, run.state)
        for kind, at in (
            ("run.dispatched", run.dispatched_at),
            ("run.started", run.started_at),
            ("run.completed", run.completed_at),
        ):
            if at is not None:
                events.append(TaskTraceEventOut(
                    at=at,
                    kind=kind,
                    node_id=run.node_id,
                    run_id=run.run_id,
                    attempt_no=run.attempt_no,
                    detail={"state": state},
                ))
    events.sort(key=lambda event: (event.at is None, event.at))
    return TaskTraceOut(task_id=task.task_id, events=events)


def to_summary(view: TaskSummaryView) -> TaskSummaryOut:
    task = view.task
    return TaskSummaryOut(
        task_id=task.task_id,
        title=task.title,
        state=task.state.value,
        owner_id=task.owner_id,
        workflow_id=task.workflow_id,
        workflow_version=task.workflow_version,
        created_at=task.created_at,
        updated_at=task.updated_at,
        current_node=view.current_node,
        progress_done=view.progress_done,
        progress_total=view.progress_total,
        claimable=view.claimable,
    )


def to_list(views, total: int, limit: int, offset: int) -> TaskListOut:
    return TaskListOut(
        items=[to_summary(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
    )


def to_counters(view: TaskCountersView) -> TaskCountersOut:
    return TaskCountersOut(
        claimable=view.claimable,
        mine_open=view.mine_open,
        approvals=view.approvals,
    )
