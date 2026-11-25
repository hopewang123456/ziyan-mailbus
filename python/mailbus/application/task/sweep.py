"""任务超时清扫：干活超时升级/自动终止，审批超时升级。

只由容器定时器调用；每次一轮独立事务。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from mailbus.application.task.flow import Flow, graph_of
from mailbus.core.approval import rules as approval_rules
from mailbus.core.approval.models import ApprovalItem
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.workflow.models import TaskRun
from mailbus.core.workflow.values import (
    ESCALATION_TERMINATE_SECONDS,
    EscalationReason,
    TaskState,
    TerminationReason,
)


class TaskSweeper:
    def __init__(self, uow_factory, clock: Clock, ids: IdGenerator) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def sweep(self) -> int:
        count = 0
        now = self._clock.now()
        with self._uow() as uow:
            for run in uow.runs.list_overdue(now):
                count += self._sweep_run(uow, run, now)
            for item in uow.approvals.due_pending(now):
                count += self._sweep_approval(uow, item, now)
            uow.commit()
        return count

    def _sweep_run(self, uow, run: TaskRun, now: datetime) -> int:
        task = uow.tasks.get(run.task_id)
        if task is None or task.state in (TaskState.DONE, TaskState.CANCELLED):
            return 0
        flow = Flow(uow, task, graph_of(uow, task), self._ids, self._clock)
        if run.escalated_at is None:
            uow.runs.save(replace(run, escalated_at=now))
            flow.escalate(EscalationReason.WORK_TIMEOUT, node_id=run.node_id,
                          run_id=run.run_id)
        elif now - run.escalated_at > timedelta(seconds=ESCALATION_TERMINATE_SECONDS):
            flow.escalate(EscalationReason.WORK_TIMEOUT, node_id=run.node_id,
                          run_id=run.run_id, level=2)
            flow.terminate(TerminationReason.AUTO_TERMINATED)
        return 1

    def _sweep_approval(self, uow, item: ApprovalItem, now: datetime) -> int:
        expired, _ = approval_rules.expire(item, now)
        if expired is item:
            return 0
        uow.approvals.save(expired)
        task = uow.tasks.get(item.task_id)
        if task is not None:
            Flow(uow, task, graph_of(uow, task), self._ids, self._clock).escalate(
                EscalationReason.APPROVAL_TIMEOUT,
                node_id=item.node_id, approval_id=item.approval_id)
        return 1
