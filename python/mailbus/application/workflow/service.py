"""流程定义用例：创建定义、追加草稿版本、发布版本。

写用例第一步做权限判定；版本发布只改版本状态与定义指针，
已发布版本不可变，运行中任务因此不会被后续发布影响。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.workflow.dto import (
    VersionCommand,
    VersionView,
    WorkflowCommand,
    WorkflowView,
)
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.errors import InvalidStateError, NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.workflow import rules
from mailbus.core.workflow.models import WorkflowNode
from mailbus.core.workflow.ports import WorkflowUnitOfWork


class WorkflowService:
    def __init__(
        self,
        uow_factory: Callable[[], WorkflowUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def list_definitions(self) -> tuple[WorkflowView, ...]:
        with self._uow() as uow:
            definitions = uow.definitions.list_all()
        return tuple(WorkflowView.of(item) for item in definitions)

    def get_definition(self, workflow_id: str) -> WorkflowView:
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
        return WorkflowView.of(definition)

    def create_definition(self, actor: Actor, cmd: WorkflowCommand) -> WorkflowView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_CREATE, Resource(kind="workflow")
        )
        now = self._clock.now()
        definition, events = rules.create_definition(self._ids.new("wf"), cmd.name, now)
        with self._uow() as uow:
            uow.definitions.add(definition)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return WorkflowView.of(definition)

    def list_versions(self, workflow_id: str) -> tuple[VersionView, ...]:
        with self._uow() as uow:
            self._load(uow, workflow_id)
            versions = uow.versions.list_by_workflow(workflow_id)
        return tuple(VersionView.of(item) for item in versions)

    def rename_definition(
        self, actor: Actor, workflow_id: str, cmd: WorkflowCommand
    ) -> WorkflowView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_MODIFY, Resource(kind="workflow")
        )
        now = self._clock.now()
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
            updated, events = rules.rename_definition(definition, cmd.name, now)
            uow.definitions.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return WorkflowView.of(updated)

    def delete_definition(self, actor: Actor, workflow_id: str) -> None:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_MODIFY, Resource(kind="workflow")
        )
        now = self._clock.now()
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
            if any(task.workflow_id == workflow_id for task in uow.tasks.list_all()):
                raise InvalidStateError("已有任务引用该流程，不能删除")
            events = rules.delete_definition(definition, now)
            uow.versions.delete_by_workflow(workflow_id)
            uow.definitions.delete(workflow_id)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()

    def get_version(self, workflow_id: str, version: int) -> VersionView:
        with self._uow() as uow:
            self._load(uow, workflow_id)
            found = uow.versions.get(workflow_id, version)
        if found is None:
            raise NotFoundError("流程版本不存在")
        return VersionView.of(found)

    def add_version(
        self, actor: Actor, workflow_id: str, cmd: VersionCommand
    ) -> VersionView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_MODIFY, Resource(kind="workflow")
        )
        now = self._clock.now()
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
            nodes = tuple(
                WorkflowNode(node_id=self._ids.new("node"), name=name, order=index)
                for index, name in enumerate(cmd.nodes)
            )
            definition, version, events = rules.add_version(definition, nodes, now)
            uow.definitions.save(definition)
            uow.versions.add(version)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return VersionView.of(version)

    def publish_version(
        self, actor: Actor, workflow_id: str, version_no: int
    ) -> VersionView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_MODIFY, Resource(kind="workflow")
        )
        now = self._clock.now()
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
            version = uow.versions.get(workflow_id, version_no)
            if version is None:
                raise NotFoundError("流程版本不存在")
            definition, published, events = rules.publish_version(
                definition, version, now
            )
            uow.definitions.save(definition)
            uow.versions.save(published)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return VersionView.of(published)

    @staticmethod
    def _load(uow: WorkflowUnitOfWork, workflow_id: str):
        definition = uow.definitions.get(workflow_id)
        if definition is None:
            raise NotFoundError("流程不存在")
        return definition
