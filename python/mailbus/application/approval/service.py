"""审批用例：请求、裁决与超时清扫。

阻塞档与任务状态同事务变更：
- 请求 → 任务 blocked；
- 通过 → 任务 resume；
- 拒绝 → 任务 failed；
- 超时 → 审批 expired，任务保持 blocked（由派发器轮询到期行）。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.approval.dto import (
    ApprovalCommand,
    ApprovalView,
    ResolveCommand,
)
from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.identity.scoping import filter_approvals_by_scope
from mailbus.core.approval import rules
from mailbus.core.approval.models import ApprovalItem
from mailbus.core.approval.ports import ApprovalUnitOfWork
from mailbus.core.approval.values import ApprovalStatus, ApprovalTier
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
)
from mailbus.core.shared.events import DomainEvent
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.workflow import lifecycle as workflow_lifecycle
from mailbus.core.workflow.models import Task
from mailbus.core.workflow.values import TaskState, TERMINAL_TASK_STATES


class ApprovalService:
    def __init__(
        self,
        uow_factory: Callable[[], ApprovalUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def request(self, actor: Actor, cmd: ApprovalCommand) -> ApprovalView:
        now = self._clock.now()
        with self._uow() as uow:
            task = self._task(uow, cmd.task_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.HITL_REQUEST,
                Resource(kind="task", owner_id=task.owner_id),
            )
            item, events = rules.request(
                self._ids.new("appr"),
                task_id=cmd.task_id,
                title=cmd.title,
                tier=cmd.tier,
                requester_id=actor.employee_id,
                node_id=cmd.node_id,
                note=cmd.note,
                now=now,
                timeout_minutes=cmd.timeout_minutes,
            )
            emitted: list[DomainEvent] = list(events)
            if cmd.tier is ApprovalTier.BLOCKING:
                task, nodes, held = workflow_lifecycle.hold(
                    task,
                    tuple(uow.tasks.nodes(cmd.task_id)),
                    reason="approval_requested",
                    now=now,
                )
                uow.tasks.save(task, nodes)
                emitted.extend(held)
            uow.approvals.add(item)
            enqueue_events(uow.outbox, emitted, self._ids, now)
            uow.commit()
        return ApprovalView.of(item)

    def resolve(
        self, actor: Actor, approval_id: str, cmd: ResolveCommand
    ) -> ApprovalView:
        ensure_allowed(
            actor.to_subject(), Capability.HITL_RESOLVE, Resource(kind="approval")
        )
        now = self._clock.now()
        with self._uow() as uow:
            item = self._load(uow, approval_id)
            # M15：发起人不得自审；仅 ALL 超管在初始引导等可信场景豁免。
            if (
                Capability.ALL not in actor.capabilities
                and item.requester_id is not None
                and item.requester_id == actor.employee_id
            ):
                raise PermissionDeniedError("审批发起人不得裁决本人发起的审批")
            resolved, events = rules.resolve(
                item,
                approved=cmd.approved,
                resolver_id=actor.employee_id,
                note=cmd.note,
                now=now,
            )
            emitted: list[DomainEvent] = list(events)
            if resolved is not item and item.tier is ApprovalTier.BLOCKING:
                emitted.extend(self._apply_task(uow, resolved, now))
            uow.approvals.save(resolved)
            enqueue_events(uow.outbox, emitted, self._ids, now)
            uow.commit()
        return ApprovalView.of(resolved)

    def withdraw(self, actor: Actor, approval_id: str) -> None:
        """撤回审批：发起人或超管可撤回；阻塞档同步恢复任务。"""
        now = self._clock.now()
        with self._uow() as uow:
            item = self._load(uow, approval_id)
            if item.requester_id != actor.employee_id:
                ensure_allowed(
                    actor.to_subject(),
                    Capability.SYSTEM_CONFIG,
                    Resource(kind="approval"),
                )
            withdrawn, events = rules.withdraw(
                item, actor_id=actor.employee_id, now=now
            )
            emitted: list[DomainEvent] = list(events)
            if item.tier is ApprovalTier.BLOCKING:
                emitted.extend(self._release_blocked(uow, item, now))
            uow.approvals.save(withdrawn)
            enqueue_events(uow.outbox, emitted, self._ids, now)
            uow.commit()

    def sweep_expired(self) -> int:
        """由派发器定时调用：到期的未裁决审批置为 expired。"""
        now = self._clock.now()
        count = 0
        with self._uow() as uow:
            for item in uow.approvals.due_pending(now):
                expired, events = rules.expire(item, now)
                if expired is item:
                    continue
                emitted: list[DomainEvent] = list(events)
                if item.tier is ApprovalTier.BLOCKING:
                    emitted.extend(self._enforce_blocked(uow, item, now))
                uow.approvals.save(expired)
                enqueue_events(uow.outbox, emitted, self._ids, now)
                count += 1
            uow.commit()
        return count

    def list_approvals(
        self, actor: Actor, status: str | None = None, task_id: str | None = None
    ) -> tuple[ApprovalView, ...]:
        parsed = self._parse_status(status)
        with self._uow() as uow:
            items = uow.approvals.list_all(parsed, task_id)
            tasks = uow.tasks.list_all()
            employees = uow.employees.list_all()
        items = filter_approvals_by_scope(actor, items, tasks, employees)
        return tuple(ApprovalView.of(item) for item in items)

    def get(self, actor: Actor, approval_id: str) -> ApprovalView:
        with self._uow() as uow:
            item = self._load(uow, approval_id)
            # 只取相关任务与归属人，避免单条查询全表加载。
            task = uow.tasks.get(item.task_id)
            owner_id = task.owner_id if task else None
            employee = uow.employees.get(owner_id) if owner_id else None
        visible = filter_approvals_by_scope(
            actor,
            [item],
            [task] if task else [],
            [employee] if employee else [],
        )
        if not visible:
            raise NotFoundError("审批不存在")
        return ApprovalView.of(item)

    @staticmethod
    def _apply_task(
        uow: ApprovalUnitOfWork, item: ApprovalItem, now
    ) -> tuple[DomainEvent, ...]:
        task = uow.tasks.get(item.task_id)
        if task is None:
            raise NotFoundError("审批关联的任务不存在")
        nodes = tuple(uow.tasks.nodes(item.task_id))
        if item.status is ApprovalStatus.APPROVED:
            task, nodes, events = workflow_lifecycle.resume(task, nodes, now)
        else:
            task, nodes, events = workflow_lifecycle.fail(
                task, nodes, reason="approval_rejected", now=now
            )
        uow.tasks.save(task, nodes)
        return events

    @staticmethod
    def _release_blocked(
        uow: ApprovalUnitOfWork, item: ApprovalItem, now
    ) -> tuple[DomainEvent, ...]:
        """撤回阻塞档：任务仍在 blocked 时恢复执行，其余状态不动。"""
        task = uow.tasks.get(item.task_id)
        if task is None or task.state is not TaskState.BLOCKED:
            return ()
        task, nodes, events = workflow_lifecycle.resume(
            task, tuple(uow.tasks.nodes(item.task_id)), now
        )
        uow.tasks.save(task, nodes)
        return events

    @staticmethod
    def _enforce_blocked(
        uow: ApprovalUnitOfWork, item: ApprovalItem, now
    ) -> tuple[DomainEvent, ...]:
        task = uow.tasks.get(item.task_id)
        if task is None or task.state in TERMINAL_TASK_STATES:
            return ()
        if task.state is TaskState.BLOCKED:
            return ()
        task, nodes, events = workflow_lifecycle.hold(
            task,
            tuple(uow.tasks.nodes(item.task_id)),
            reason="approval_timeout",
            now=now,
        )
        uow.tasks.save(task, nodes)
        return events

    @staticmethod
    def _load(uow: ApprovalUnitOfWork, approval_id: str) -> ApprovalItem:
        item = uow.approvals.get(approval_id)
        if item is None:
            raise NotFoundError("审批不存在")
        return item

    @staticmethod
    def _task(uow: ApprovalUnitOfWork, task_id: str) -> Task:
        task = uow.tasks.get(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        return task

    @staticmethod
    def _parse_status(status: str | None) -> ApprovalStatus | None:
        if status is None:
            return None
        try:
            return ApprovalStatus(status)
        except ValueError as exc:
            raise InvalidStateError(f"未知审批状态：{status}") from exc
