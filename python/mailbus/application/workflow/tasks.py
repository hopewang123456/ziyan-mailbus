"""任务用例：创建、派发、推进、取消。

自由任务与流程任务共用 Task 聚合：workflow_version 为空即自由任务，
推进时直接改任务状态；否则按节点顺序推进。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.workflow.dto import (
    AdvanceCommand,
    TaskCommand,
    TaskView,
)
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.errors import InvalidStateError, NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.workflow import rules
from mailbus.core.workflow.errors import VersionNotPublishedError
from mailbus.core.workflow.models import Task, WorkflowVersion
from mailbus.core.workflow.ports import WorkflowUnitOfWork
from mailbus.core.workflow.values import TaskState


class TaskService:
    def __init__(
        self,
        uow_factory: Callable[[], WorkflowUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def create(self, actor: Actor, cmd: TaskCommand) -> TaskView:
        owner_id = cmd.owner_id or actor.employee_id
        ensure_allowed(
            actor.to_subject(),
            Capability.TASK_CREATE,
            Resource(kind="task", owner_id=owner_id),
        )
        now = self._clock.now()
        with self._uow() as uow:
            version = self._version(uow, cmd)
            task, nodes, events = rules.create_task(
                self._ids.new("task"),
                cmd.title,
                owner_id=owner_id,
                created_by=actor.employee_id,
                version=version,
                now=now,
            )
            uow.tasks.add(task, nodes)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return TaskView.of(task, nodes)

    def dispatch(self, actor: Actor, task_id: str) -> TaskView:
        now = self._clock.now()
        with self._uow() as uow:
            task = self._load(uow, task_id)
            self._require(actor, Capability.TASK_DISPATCH, task)
            updated, nodes, events = rules.dispatch(
                task, tuple(uow.tasks.nodes(task_id)), now
            )
            uow.tasks.save(updated, nodes)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return TaskView.of(updated, nodes)

    def advance(self, actor: Actor, task_id: str, cmd: AdvanceCommand) -> TaskView:
        now = self._clock.now()
        with self._uow() as uow:
            task = self._load(uow, task_id)
            self._require(actor, Capability.RESULT_SUBMIT, task)
            updated, nodes, events = rules.advance(
                task,
                tuple(uow.tasks.nodes(task_id)),
                node_id=cmd.node_id,
                outcome=cmd.outcome,
                now=now,
            )
            uow.tasks.save(updated, nodes)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return TaskView.of(updated, nodes)

    def cancel(self, actor: Actor, task_id: str) -> TaskView:
        now = self._clock.now()
        with self._uow() as uow:
            task = self._load(uow, task_id)
            self._require(actor, Capability.TASK_DISPATCH, task)
            updated, nodes, events = rules.cancel(
                task, tuple(uow.tasks.nodes(task_id)), now
            )
            uow.tasks.save(updated, nodes)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return TaskView.of(updated, nodes)

    def list_tasks(
        self, state: str | None = None, owner_id: str | None = None
    ) -> tuple[TaskView, ...]:
        parsed = self._parse_state(state)
        with self._uow() as uow:
            tasks = uow.tasks.list_all(parsed, owner_id)
            views = tuple(TaskView.of(task, uow.tasks.nodes(task.task_id)) for task in tasks)
        return views

    def get(self, task_id: str) -> TaskView:
        with self._uow() as uow:
            task = self._load(uow, task_id)
            nodes = uow.tasks.nodes(task_id)
        return TaskView.of(task, nodes)

    @staticmethod
    def _require(actor: Actor, capability: Capability, task: Task) -> None:
        ensure_allowed(
            actor.to_subject(),
            capability,
            Resource(kind="task", owner_id=task.owner_id),
        )

    @staticmethod
    def _load(uow: WorkflowUnitOfWork, task_id: str) -> Task:
        task = uow.tasks.get(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        return task

    @staticmethod
    def _parse_state(state: str | None) -> TaskState | None:
        if state is None:
            return None
        try:
            return TaskState(state)
        except ValueError as exc:
            raise InvalidStateError(f"未知任务状态：{state}") from exc

    @staticmethod
    def _version(uow: WorkflowUnitOfWork, cmd: TaskCommand) -> WorkflowVersion | None:
        if not cmd.workflow_id:
            return None
        definition = uow.definitions.get(cmd.workflow_id)
        if definition is None:
            raise NotFoundError("流程不存在")
        number = (
            cmd.workflow_version
            if cmd.workflow_version is not None
            else definition.published_version
        )
        if number is None:
            raise VersionNotPublishedError("流程尚未发布版本")
        version = uow.versions.get(cmd.workflow_id, number)
        if version is None:
            raise NotFoundError("流程版本不存在")
        if not version.published:
            raise VersionNotPublishedError("只能从已发布版本创建任务")
        return version
