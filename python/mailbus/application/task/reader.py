"""任务读出：详情、列表、角标与可见性判定。"""

from __future__ import annotations

from mailbus.application.task import staff
from mailbus.application.task.dto import (
    TaskCountersView,
    TaskDetailView,
    TaskSummaryView,
    artifact_view,
    node_views,
    run_view,
    summary_view,
)
from mailbus.core.approval.models import ApprovalItem
from mailbus.core.approval.values import ApprovalStatus
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableError,
)
from mailbus.core.shared.values import DataScope
from mailbus.core.workflow.models import Task, TaskArtifact, TaskRun
from mailbus.core.workflow.values import OPEN_RUN_STATES, RunState, TaskState

OPEN_TASK_STATES = (TaskState.PENDING, TaskState.RUNNING, TaskState.BLOCKED)


class TaskReader:
    def __init__(self, uow_factory) -> None:
        self._uow = uow_factory

    def load(self, uow, task_id: str) -> Task:
        task = uow.tasks.get(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        return task

    def get(self, actor, task_id: str) -> TaskDetailView:
        with self._uow() as uow:
            task = self.load(uow, task_id)
            runs = uow.runs.list_by_task(task_id)
            self.ensure_visible(actor, uow, task, runs)
        return self.detail(task_id)

    def detail(self, task_id: str) -> TaskDetailView:
        """无可见性判定的详情投影；调用方负责鉴权（事件/内部收敛用）。"""
        with self._uow() as uow:
            task = self.load(uow, task_id)
            runs = uow.runs.list_by_task(task_id)
            nodes = uow.tasks.nodes(task_id)
            variables = {item.key: item.value for item in uow.variables.list_by_task(task_id)}
            artifacts = tuple(
                artifact_view(item) for item in uow.artifacts.list_by_task(task_id)
            )
        return TaskDetailView(task=task, nodes=node_views(nodes, runs),
                              runs=tuple(run_view(run) for run in runs),
                              variables=variables, artifacts=artifacts)

    def get_artifact(self, actor, artifact_id: str) -> TaskArtifact:
        with self._uow() as uow:
            artifact = uow.artifacts.get(artifact_id)
            if artifact is None:
                raise NotFoundError("产物不存在")
            task = self.load(uow, artifact.task_id)
            self.ensure_visible(actor, uow, task,
                                uow.runs.list_by_task(artifact.task_id))
        return artifact

    def list_tasks(self, actor, state: str | None, owner_id: str | None,
                   workflow_id: str | None, limit: int, offset: int,
                   ) -> tuple[list[TaskSummaryView], int]:
        parsed = self.parse_state(state)
        viewer = None if actor.data_scope is DataScope.GLOBAL else actor.employee_id
        with self._uow() as uow:
            tasks = uow.tasks.list_all(parsed, owner_id, workflow_id, limit, offset, viewer)
            total = uow.tasks.count(parsed, owner_id, workflow_id, viewer)
            summaries = [self.summary(uow, actor, task) for task in tasks]
        return summaries, total

    def counters(self, actor) -> TaskCountersView:
        with self._uow() as uow:
            employee = uow.employees.get(actor.employee_id)
            tasks = uow.tasks.list_all(viewer_id=None)
            claimable = 0
            for task in tasks:
                if task.state not in OPEN_TASK_STATES:
                    continue
                for run in uow.runs.list_by_task(task.task_id):
                    if run.state is RunState.WAITING_HUMAN \
                            and run.assigned_employee_id is None \
                            and staff.can_claim(uow, employee, self.wf(uow, task, run.node_id)):
                        claimable += 1
            mine = uow.tasks.count(owner_id=actor.employee_id)
            pending = self.visible_approvals(
                actor, uow, uow.approvals.list_all(ApprovalStatus.PENDING))
        return TaskCountersView(claimable=claimable, mine_open=mine,
                                approvals=len(pending))

    def summary(self, uow, actor, task: Task) -> TaskSummaryView:
        runs = uow.runs.list_by_task(task.task_id)
        employee = uow.employees.get(actor.employee_id)
        claimable = {
            run.node_id for run in runs
            if run.state is RunState.WAITING_HUMAN and run.assigned_employee_id is None
            and staff.can_claim(uow, employee, self.wf(uow, task, run.node_id))
        }
        return summary_view(task, uow.tasks.nodes(task.task_id), runs, claimable)

    def ensure_visible(self, actor, uow, task: Task, runs: list[TaskRun]) -> None:
        if actor.data_scope is DataScope.GLOBAL:
            return
        if actor.employee_id in (task.owner_id, task.created_by):
            return
        if any(run.assigned_employee_id == actor.employee_id for run in runs):
            return
        if actor.data_scope is DataScope.TEAM and actor.team_id:
            owner = uow.employees.get(task.owner_id) if task.owner_id else None
            if owner is not None and owner.team_id == actor.team_id:
                return
        raise PermissionDeniedError("无权查看该任务")

    @staticmethod
    def wf(uow, task: Task, node_id: str):
        if node_id == "free" or not task.workflow_id or task.workflow_version is None:
            return None
        from mailbus.core.task import GraphIndex

        nodes, edges = uow.graphs.load(task.workflow_id, task.workflow_version)
        return GraphIndex(nodes, edges).node(node_id)

    @staticmethod
    def visible_approvals(actor, uow, items: list[ApprovalItem]) -> list[ApprovalItem]:
        return [item for item in items if TaskReader.approval_visible(actor, uow, item)]

    @staticmethod
    def approval_visible(actor, uow, item: ApprovalItem) -> bool:
        if actor.data_scope is DataScope.GLOBAL:
            return True
        if item.requester_id == actor.employee_id:
            return True
        task = uow.tasks.get(item.task_id)
        if task is None:
            return False
        if actor.employee_id in (task.owner_id, task.created_by):
            return True
        if actor.data_scope is DataScope.TEAM and actor.team_id:
            owner = uow.employees.get(task.owner_id) if task.owner_id else None
            return owner is not None and owner.team_id == actor.team_id
        return False

    @staticmethod
    def parse_state(state: str | None) -> TaskState | None:
        if state is None:
            return None
        try:
            return TaskState(state)
        except ValueError as exc:
            raise UnprocessableError(f"未知任务状态：{state}") from exc
