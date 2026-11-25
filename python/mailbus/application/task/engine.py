"""任务域用例：创建、认领、提交、取消、重跑、审批与升级清扫。

唯一推进实现由 Flow 承担；本层只做权限、事务与读出委派。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mailbus.application.approval.dto import ResolveCommand
from mailbus.application.task import staff
from mailbus.application.task.conditions import is_failed_result
from mailbus.application.task.artifacts import ArtifactUploader
from mailbus.application.task.dto import (
    CreateTaskCommand,
    RerunJoinCommand,
    SubmitResultCommand,
    TaskDetailView,
    parse_approval_state,
)
from mailbus.application.task.flow import Flow, graph_of
from mailbus.application.task.public import publish_task_updated
from mailbus.application.task.reader import TaskReader
from mailbus.application.task.sweep import TaskSweeper
from mailbus.core.approval import rules as approval_rules
from mailbus.core.approval.models import ApprovalItem
from mailbus.core.approval.values import ApprovalStatus
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableError,
)
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.task import GraphIndex
from mailbus.core.workflow.errors import VersionNotPublishedError
from mailbus.core.workflow.models import Task, TaskArtifact, TaskNode, TaskRun, TaskVariable
from mailbus.core.workflow.values import (
    NodeState,
    OPEN_RUN_STATES,
    RunState,
    TaskState,
    TerminationReason,
)

class TaskEngine:
    def __init__(self, uow_factory, clock: Clock, ids: IdGenerator, events=None,
                 seat_of=None, approvals=None, artifacts_dir=None) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._events = events
        self._seat_of = seat_of
        self._approvals = approvals
        self._artifacts_dir = artifacts_dir
        self._reader = TaskReader(uow_factory)
        self._sweeper = TaskSweeper(uow_factory, clock, ids)
        self._uploader = ArtifactUploader(
            uow_factory, clock, ids, self._reader, artifacts_dir,
            self._ensure_open, self._publish,
        )

    # ---- 创建 ----

    def create(self, actor, cmd: CreateTaskCommand):
        owner_id = cmd.owner_id or actor.employee_id
        ensure_allowed(actor.to_subject(), Capability.TASK_CREATE,
                       Resource(kind="task", owner_id=owner_id))
        if owner_id != actor.employee_id:
            ensure_allowed(actor.to_subject(), Capability.TASK_DISPATCH,
                           Resource(kind="task", owner_id=owner_id))
        now = self._clock.now()
        with self._uow() as uow:
            task_id = self._ids.new("task")
            if cmd.workflow_id:
                task, graph = self._workflow_task(uow, task_id, cmd, owner_id, actor, now)
            else:
                task, graph = self._free_task(uow, task_id, cmd, owner_id, actor, now)
            if cmd.variables:
                uow.variables.add_many([
                    TaskVariable(task_id, key, value, "input", actor.employee_id, now)
                    for key, value in cmd.variables.items()
                ])
            flow = Flow(uow, task, graph, self._ids, self._clock)
            if cmd.workflow_id:
                flow.start_graph()
            else:
                flow.start_free(owner_id)
            uow.commit()
        self._publish(task_id)
        return self._reader.get(actor, task_id)

    def list_tasks(self, actor, state, owner_id, workflow_id, limit, offset):
        return self._reader.list_tasks(actor, state, owner_id, workflow_id, limit, offset)

    def get(self, actor, task_id: str):
        return self._reader.get(actor, task_id)

    def counters(self, actor):
        return self._reader.counters(actor)

    # ---- 认领与提交 ----

    def claim(self, actor, task_id: str, node_id: str):
        now = self._clock.now()
        with self._uow() as uow:
            task = self._reader.load(uow, task_id)
            self._ensure_open(task)
            run = self._claimable_run(uow, task_id, node_id)
            employee = uow.employees.get(actor.employee_id)
            if Capability.ALL not in actor.capabilities and (
                    employee is None
                    or not staff.can_claim(uow, employee,
                                           self._reader.wf(uow, task, node_id))):
                raise PermissionDeniedError("不属于该节点的候选岗位")
            if not uow.runs.claim(run.run_id, actor.employee_id, now):
                raise InvalidStateError("节点已被其他成员认领")
            node = uow.tasks.get_node(task_id, node_id)
            if node is not None:
                uow.tasks.save_node(replace(node, state=NodeState.RUNNING,
                                            current_run_id=run.run_id, updated_at=now))
            uow.tasks.save_task(replace(task, state=TaskState.RUNNING,
                                        owner_id=actor.employee_id, updated_at=now))
            uow.commit()
        self._publish(task_id)
        return self._reader.get(actor, task_id)

    def submit(self, actor, task_id: str, node_id: str, cmd: SubmitResultCommand):
        now = self._clock.now()
        with self._uow() as uow:
            task = self._reader.load(uow, task_id)
            self._ensure_open(task)
            run = self._run_for_submit(uow, task_id, node_id, cmd.attempt_no)
            self._ensure_submitter(actor, run)
            self._validate_artifacts(uow, task_id, cmd.artifact_ids)
            if run.state in (RunState.DONE, RunState.FAILED):
                if run.result == cmd.result:
                    uow.commit()
                    return self._reader.get(actor, task_id)
                raise InvalidStateError("该执行实例已提交过结果")
            run = replace(run, assigned_employee_id=run.assigned_employee_id or actor.employee_id,
                          state=RunState.RUNNING, started_at=run.started_at or now)
            uow.runs.save(run)
            flow = Flow(uow, task, graph_of(uow, task), self._ids, self._clock)
            if is_failed_result(cmd.result):
                flow.fail(run, cmd.result)
            else:
                flow.complete(run, cmd.result)
            uow.tasks.save_task(replace(flow.task, owner_id=actor.employee_id,
                                        updated_at=now))
            uow.commit()
        self._publish(task_id)
        return self._reader.get(actor, task_id)

    # ---- 取消与重跑 ----

    def cancel(self, actor, task_id: str, reason: str):
        try:
            parsed = TerminationReason(reason)
        except ValueError as exc:
            raise UnprocessableError(f"未知终止原因：{reason}") from exc
        with self._uow() as uow:
            task = self._reader.load(uow, task_id)
            self._ensure_operator(actor, task)
            self._ensure_open(task)
            flow = Flow(uow, task, graph_of(uow, task), self._ids, self._clock)
            flow.terminate(parsed)
            uow.commit()
        self._publish(task_id)
        return self._reader.get(actor, task_id)

    def rerun_join(self, actor, task_id: str, node_id: str, cmd: RerunJoinCommand):
        now = self._clock.now()
        with self._uow() as uow:
            task = self._reader.load(uow, task_id)
            self._ensure_operator(actor, task)
            self._ensure_open(task)
            graph = graph_of(uow, task)
            wf = graph.node(node_id) if graph else None
            if wf is None or wf.node_type != "parallel_join":
                raise UnprocessableError("只有汇聚节点可以重跑")
            runs = uow.runs.list_by_node(task_id, node_id)
            if any(item.state in OPEN_RUN_STATES for item in runs):
                raise InvalidStateError("汇聚仍在执行中")
            flow = Flow(uow, task, graph, self._ids, self._clock)
            ready, _ = flow.join_state(node_id)
            if ready:
                raise InvalidStateError("汇聚已满足推进条件，无需重跑")
            missing = flow.force_join(node_id, cmd.fanout_group, cmd.scope)
            uow.audit.record(
                actor.employee_id, "task.join_rerun", f"task:{task_id}",
                {"task_id": task_id, "node_id": node_id,
                 "attempt_no": flow.last_attempt, "fanout_group": cmd.fanout_group,
                 "scope": cmd.scope, "missing": missing},
            )
            uow.commit()
        self._publish(task_id)
        return self._reader.get(actor, task_id)

    # ---- 审批 ----

    def list_approvals(self, actor, state, limit, offset):
        with self._uow() as uow:
            items = uow.approvals.list_all(parse_approval_state(state))
            visible = TaskReader.visible_approvals(actor, uow, items)
        return visible[offset:offset + limit], len(visible)

    def resolve_approval(self, actor, approval_id: str, decision: str,
                         comment: str | None) -> ApprovalItem:
        ensure_allowed(actor.to_subject(), Capability.HITL_RESOLVE,
                       Resource(kind="approval"))
        if decision == "rejected" and not (comment or "").strip():
            raise UnprocessableError("驳回必须填写意见")
        now = self._clock.now()
        with self._uow() as uow:
            item = uow.approvals.get(approval_id)
            if item is None:
                raise NotFoundError("审批不存在")
            if item.status is not ApprovalStatus.PENDING:
                raise InvalidStateError("审批已处理")
            task = self._reader.load(uow, item.task_id)
            graph = graph_of(uow, task)
            node = graph.node(item.node_id) if graph and item.node_id else None
            if node is not None and node.node_type == "final_approval":
                self._ensure_approver(actor, uow, node)
            else:
                node = None
        if node is None:
            return self._resolve_legacy(actor, approval_id, decision, comment)
        with self._uow() as uow:
            item = uow.approvals.get(approval_id)
            if item is None:
                raise NotFoundError("审批不存在")
            if item.status is not ApprovalStatus.PENDING:
                raise InvalidStateError("审批已处理")
            task = self._reader.load(uow, item.task_id)
            graph = graph_of(uow, task)
            approved = decision == "approved"
            item, _ = approval_rules.resolve(item, approved=approved,
                                             resolver_id=actor.employee_id,
                                             note=comment, now=now)
            uow.approvals.save(item)
            self._close_approval_run(uow, task.task_id, item.node_id or "",
                                     RunState.DONE if approved else RunState.FAILED, now)
            flow = Flow(uow, task, graph, self._ids, self._clock)
            if approved:
                flow.approve(item.node_id or "")
            else:
                flow.reject(item.node_id or "")
            uow.tasks.save_task(replace(flow.task, updated_at=now))
            uow.commit()
        self._publish(item.task_id)
        return item

    def _resolve_legacy(self, actor, approval_id: str, decision: str,
                        comment: str | None) -> ApprovalItem:
        """非终验审批（旧 tier 审批）沿用 ApprovalService 的阻塞/自审语义。"""
        if self._approvals is None:
            raise UnprocessableError("该审批不由任务引擎处理")
        self._approvals.resolve(actor, approval_id, ResolveCommand(
            approved=decision == "approved", note=comment))
        with self._uow() as uow:
            item = uow.approvals.get(approval_id)
        if item is None:
            raise NotFoundError("审批不存在")
        self._publish(item.task_id)
        return item

    # ---- 产物 ----

    def download(self, actor, artifact_id: str) -> TaskArtifact:
        with self._uow() as uow:
            artifact = uow.artifacts.get(artifact_id)
            if artifact is None:
                raise NotFoundError("产物不存在")
            task = self._reader.load(uow, artifact.task_id)
            if Capability.ARTIFACT_READ_ALL not in actor.capabilities:
                self._reader.ensure_visible(actor, uow, task,
                                            uow.runs.list_by_task(artifact.task_id))
            return artifact

    def upload_artifact(self, actor, task_id, node_id, file_name,
                        file_bytes, description):
        return self._uploader.upload(
            actor, task_id, node_id, file_name, file_bytes, description,
        )

    # ---- 超时清扫 ----

    def sweep_timeouts(self) -> int:
        return self._sweeper.sweep()


    # ---- 内部 ----

    def _workflow_task(self, uow, task_id: str, cmd, owner_id: str, actor, now):
        definition = uow.definitions.get(cmd.workflow_id)
        if definition is None:
            raise NotFoundError("流程不存在")
        number = definition.published_version
        if number is None:
            raise VersionNotPublishedError("流程尚未发布版本")
        version = uow.versions.get(cmd.workflow_id, number)
        if version is None or not version.published:
            raise VersionNotPublishedError("只能从已发布版本创建任务")
        nodes, edges = uow.graphs.load(cmd.workflow_id, number)
        if not nodes:
            raise UnprocessableError("流程没有可执行节点")
        task = Task(task_id, cmd.title, TaskState.RUNNING, cmd.workflow_id, number,
                    owner_id, actor.employee_id, now, now)
        uow.tasks.add(task, [])
        for node in nodes:
            uow.tasks.save_node(TaskNode(task_id, node.node_id, node.name, node.order,
                                         NodeState.PENDING, None, now))
        return task, GraphIndex(nodes, edges)

    def _free_task(self, uow, task_id: str, cmd, owner_id: str, actor, now):
        task = Task(task_id, cmd.title, TaskState.RUNNING, None, None,
                    owner_id, actor.employee_id, now, now)
        uow.tasks.add(task, [TaskNode(task_id, "free", cmd.title, 0,
                                      NodeState.PENDING, None, now)])
        return task, None

    @staticmethod
    def _ensure_open(task: Task) -> None:
        if task.state in (TaskState.DONE, TaskState.CANCELLED):
            raise InvalidStateError("任务已结束")

    @staticmethod
    def _ensure_operator(actor, task: Task) -> None:
        if Capability.ALL in actor.capabilities or actor.employee_id == task.created_by:
            return
        raise PermissionDeniedError("只有发起人或超管可以执行该操作")

    @staticmethod
    def _ensure_approver(actor, uow, node) -> None:
        """终验或签：岗位下在职真人，或用 config.assignee_id 收窄到单人。"""
        if Capability.ALL in actor.capabilities:
            return
        narrowed = (node.config or {}).get("assignee_id")
        if narrowed and narrowed != actor.employee_id:
            raise PermissionDeniedError("你不是该终验的指定审批人")
        if narrowed == actor.employee_id:
            return
        employee = uow.employees.get(actor.employee_id)
        if employee is None or not staff.can_claim(uow, employee, node):
            raise PermissionDeniedError("你不是该终验节点的审批人")

    def _publish(self, task_id: str) -> None:
        publish_task_updated(self._events, self._seat_of, self._reader, task_id)

    @staticmethod
    def _claimable_run(uow, task_id: str, node_id: str) -> TaskRun:
        runs = uow.runs.list_by_node(task_id, node_id)
        for run in sorted(runs, key=lambda item: item.attempt_no, reverse=True):
            if run.state is RunState.WAITING_HUMAN and run.assigned_employee_id is None:
                return run
        raise InvalidStateError("节点当前没有可认领的待办")

    @staticmethod
    def _run_for_submit(uow, task_id: str, node_id: str, attempt_no: int) -> TaskRun:
        runs = [run for run in uow.runs.list_by_node(task_id, node_id)
                if run.attempt_no == attempt_no]
        if not runs:
            latest = uow.runs.max_attempt(task_id, node_id)
            raise InvalidStateError(
                f"执行实例已过期：当前 attempt_no={latest}" if latest else "节点尚未派发")
        open_runs = [run for run in runs if run.state in OPEN_RUN_STATES]
        return open_runs[0] if open_runs else runs[0]

    @staticmethod
    def _ensure_submitter(actor, run: TaskRun) -> None:
        if Capability.ALL in actor.capabilities:
            return
        if run.assigned_employee_id not in (None, actor.employee_id):
            raise PermissionDeniedError("只有当前执行人可以提交结果")

    @staticmethod
    def _validate_artifacts(uow, task_id: str, artifact_ids: tuple[str, ...]) -> None:
        for artifact_id in artifact_ids:
            artifact = uow.artifacts.get(artifact_id)
            if artifact is None or artifact.task_id != task_id:
                raise UnprocessableError(f"产物不存在：{artifact_id}")

    @staticmethod
    def _close_approval_run(uow, task_id: str, node_id: str,
                            run_state: RunState, now: datetime) -> None:
        for run in uow.runs.list_by_node(task_id, node_id):
            if run.state in OPEN_RUN_STATES:
                uow.runs.save(replace(run, state=run_state, completed_at=now))
