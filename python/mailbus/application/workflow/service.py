"""流程定义用例：定义、版本、Graph 读写、发布校验与派生。

写用例第一步做权限判定；Graph 只走 wf_nodes + wf_node_transitions，
wf_versions.nodes 保持只读历史。已发布版本不可变，运行中任务不受后续发布影响。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.workflow import validation
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
)
from mailbus.application.workflow.graph_ops import (
    edges_of,
    issue_detail,
    legacy_graph,
    nodes_of,
    version_created,
)
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.errors import InvalidStateError, NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.workflow import rules
from mailbus.core.workflow.errors import (
    GraphInvalidError,
    PublishValidationError,
    RevisionConflictError,
)
from mailbus.core.workflow.models import WorkflowNode, WorkflowVersion
from mailbus.core.workflow.ports import WorkflowUnitOfWork
from mailbus.core.workflow.values import TERMINAL_TASK_STATES, VersionState


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

    def list_definitions(
        self, limit: int = 100, offset: int = 0
    ) -> tuple[tuple[WorkflowView, ...], int]:
        with self._uow() as uow:
            definitions = uow.definitions.list_all(limit, offset)
            total = uow.definitions.count()
        return tuple(WorkflowView.of(item) for item in definitions), total

    def get_definition(self, workflow_id: str) -> WorkflowView:
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
        return WorkflowView.of(definition)

    def create_definition(
        self,
        actor: Actor,
        cmd: WorkflowCommand,
        nodes: Sequence[GraphNodeCommand] | None = None,
        edges: Sequence[GraphEdgeCommand] | None = None,
    ) -> WorkflowView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_CREATE, Resource(kind="workflow")
        )
        graph_nodes = nodes_of(nodes) if nodes is not None else None
        graph_edges = edges_of(edges)
        if graph_nodes is not None:
            self._raise_if_invalid(graph_nodes, graph_edges)
        now = self._clock.now()
        definition, events = rules.create_definition(self._ids.new("wf"), cmd.name, now)
        with self._uow() as uow:
            uow.definitions.add(definition)
            if graph_nodes is not None:
                version = WorkflowVersion(
                    workflow_id=definition.workflow_id,
                    version=1,
                    state=VersionState.DRAFT,
                    revision=1,
                    created_at=now,
                )
                definition = replace(definition, latest_version=1)
                uow.definitions.save(definition)
                uow.versions.add(version)
                uow.graphs.replace(
                    definition.workflow_id, version.version, graph_nodes, graph_edges
                )
                events = (
                    *events,
                    version_created(definition.workflow_id, 1, now),
                )
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return WorkflowView.of(definition)

    def list_versions(
        self, workflow_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[tuple[VersionView, ...], int]:
        with self._uow() as uow:
            self._load(uow, workflow_id)
            versions = uow.versions.list_by_workflow(workflow_id, limit, offset)
            total = uow.versions.count_by_workflow(workflow_id)
        return tuple(VersionView.of(item) for item in versions), total

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
            if any(
                task.workflow_id == workflow_id
                and task.state not in TERMINAL_TASK_STATES
                for task in uow.tasks.list_all()
            ):
                raise InvalidStateError("已有活跃任务引用该流程，不能删除")
            uow.definitions.soft_delete(workflow_id, now, actor.employee_id)
            uow.audit.record(
                actor.employee_id,
                "workflow.deleted",
                f"workflow:{workflow_id}",
                {"workflow_id": workflow_id},
            )
            enqueue_events(
                uow.outbox, rules.delete_definition(definition, now), self._ids, now
            )
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
            # 旧线性版本编辑器仍可用：同步写 Graph 表，执行只读 wf_nodes 单源。
            uow.graphs.replace(
                workflow_id, version.version, *legacy_graph(nodes)
            )
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return VersionView.of(version)

    def get_graph(self, workflow_id: str, version: int) -> GraphView:
        with self._uow() as uow:
            self._load(uow, workflow_id)
            found = uow.versions.get(workflow_id, version)
            if found is None:
                raise NotFoundError("流程版本不存在")
            nodes, edges = uow.graphs.load(workflow_id, version)
        return GraphView.of(nodes, edges, found.revision)

    def save_graph(
        self,
        actor: Actor,
        workflow_id: str,
        version_no: int,
        nodes: Sequence[GraphNodeCommand],
        edges: Sequence[GraphEdgeCommand],
        expected_revision: int,
        force: bool = False,
    ) -> GraphView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_MODIFY, Resource(kind="workflow")
        )
        graph_nodes = nodes_of(nodes)
        graph_edges = edges_of(edges)
        self._raise_if_invalid(graph_nodes, graph_edges)
        with self._uow() as uow:
            self._load(uow, workflow_id)
            version = uow.versions.get(workflow_id, version_no)
            if version is None:
                raise NotFoundError("流程版本不存在")
            if version.published:
                raise InvalidStateError("已发布版本不可修改，请先派生新版本")
            if not force and expected_revision != version.revision:
                raise RevisionConflictError(
                    "版本已被其他人修改，请刷新后重试", version.revision
                )
            uow.graphs.replace(workflow_id, version_no, graph_nodes, graph_edges)
            new_revision = uow.graphs.bump_revision(workflow_id, version_no)
            uow.audit.record(
                actor.employee_id,
                "workflow.graph_save",
                f"workflow:{workflow_id}:v{version_no}",
                {
                    "workflow_id": workflow_id,
                    "version": version_no,
                    "force": force,
                    "base_revision": version.revision,
                    "revision": new_revision,
                    "node_count": len(graph_nodes),
                    "edge_count": len(graph_edges),
                },
            )
            uow.commit()
        return GraphView.of(graph_nodes, graph_edges, new_revision)

    def validate_graph(
        self,
        workflow_id: str,
        version: int,
        nodes: Sequence[GraphNodeCommand] | None = None,
        edges: Sequence[GraphEdgeCommand] | None = None,
    ) -> ValidateView:
        with self._uow() as uow:
            self._load(uow, workflow_id)
            found = uow.versions.get(workflow_id, version)
            if found is None:
                raise NotFoundError("流程版本不存在")
            if nodes is None:
                stored_nodes, stored_edges = uow.graphs.load(workflow_id, version)
                graph_nodes = tuple(stored_nodes)
                graph_edges = tuple(stored_edges)
            else:
                graph_nodes = nodes_of(nodes)
                graph_edges = edges_of(edges)
        report = validation.validate(graph_nodes, graph_edges)
        return ValidateView(
            ok=report.ok,
            errors=tuple(ValidateIssueView.of(item) for item in report.errors),
            warnings=tuple(ValidateIssueView.of(item) for item in report.warnings),
            stats=dict(report.stats),
        )

    def clone_version(
        self, actor: Actor, workflow_id: str, source_version: int
    ) -> VersionView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_MODIFY, Resource(kind="workflow")
        )
        now = self._clock.now()
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
            source = uow.versions.get(workflow_id, source_version)
            if source is None:
                raise NotFoundError("流程版本不存在")
            version = WorkflowVersion(
                workflow_id=workflow_id,
                version=definition.latest_version + 1,
                state=VersionState.DRAFT,
                nodes=source.nodes,
                revision=1,
                created_at=now,
            )
            uow.versions.add(version)
            uow.graphs.copy(workflow_id, source_version, version.version)
            uow.definitions.save(
                replace(definition, latest_version=version.version)
            )
            uow.audit.record(
                actor.employee_id,
                "workflow.version_cloned",
                f"workflow:{workflow_id}:v{version.version}",
                {
                    "workflow_id": workflow_id,
                    "source_version": source_version,
                    "version": version.version,
                },
            )
            enqueue_events(
                uow.outbox,
                (version_created(workflow_id, version.version, now),),
                self._ids,
                now,
            )
            uow.commit()
        return VersionView.of(version)

    def publish_version(
        self, actor: Actor, workflow_id: str, version_no: int
    ) -> VersionView:
        ensure_allowed(
            actor.to_subject(), Capability.WORKFLOW_PUBLISH, Resource(kind="workflow")
        )
        now = self._clock.now()
        with self._uow() as uow:
            definition = self._load(uow, workflow_id)
            version = uow.versions.get(workflow_id, version_no)
            if version is None:
                raise NotFoundError("流程版本不存在")
            if version.published:
                return VersionView.of(version)
            nodes, edges = uow.graphs.load(workflow_id, version_no)
            # 旧线性版本（wf_versions.nodes 有值且未经过 Graph 编辑）保持原发布语义；
            # 新 Graph 版本（nodes 为空，或 revision 已被 PUT 提升）必须通过校验。
            legacy = bool(version.nodes) and version.revision == 1
            if not legacy:
                report = validation.validate(tuple(nodes), tuple(edges))
                if not report.ok:
                    raise PublishValidationError(
                        "流程图校验未通过，不能发布",
                        tuple(
                            issue_detail(ValidateIssueView.of(item))
                            for item in report.errors
                        ),
                    )
            definition, published, events = rules.publish_version(
                definition, version, now
            )
            uow.definitions.save(definition)
            uow.versions.save(published)
            uow.audit.record(
                actor.employee_id,
                "workflow.version_published",
                f"workflow:{workflow_id}:v{version_no}",
                {"workflow_id": workflow_id, "version": version_no},
            )
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return VersionView.of(published)

    @staticmethod
    def _raise_if_invalid(
        nodes: Sequence[WorkflowNode], edges: Sequence[WorkflowEdge]
    ) -> None:
        issues = validation.structural_issues(tuple(nodes), tuple(edges))
        if issues:
            raise GraphInvalidError(
                "图结构不合法", tuple(issue_detail(ValidateIssueView.of(item)) for item in issues)
            )

    @staticmethod
    def _load(uow: WorkflowUnitOfWork, workflow_id: str):
        definition = uow.definitions.get(workflow_id)
        if definition is None or definition.deleted:
            raise NotFoundError("流程不存在")
        return definition

