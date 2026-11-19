"""运营总览只读投影：跨上下文计数与指标快照，不引入新聚合。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from mailbus.application.queries.ports import ReadUnitOfWork
from mailbus.core.approval.values import ApprovalStatus
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.shared.ports import Clock
from mailbus.core.workflow.values import TaskState

_ACTIVE_TASK_STATES = frozenset(
    {TaskState.QUEUED, TaskState.RUNNING, TaskState.BLOCKED}
)


@dataclass(frozen=True, slots=True)
class MetricPoint:
    metric: str
    value: int | float
    unit: str = "count"


@dataclass(frozen=True, slots=True)
class OverviewView:
    employees_total: int
    employees_active: int
    employees_pending: int
    employees_offline: int
    agents_total: int
    agents_enabled: int
    agents_online: int
    agents_busy: int
    teams: int
    positions: int
    seats_occupied: int
    tasks_total: int
    tasks_active: int
    tasks_running: int
    tasks_blocked: int
    tasks_done: int
    tasks_failed_today: int
    approvals_pending: int
    messages_total: int
    skills_total: int
    skills_enabled: int
    workflows_total: int
    workflows_published: int
    metrics: tuple[MetricPoint, ...]


@dataclass(frozen=True, slots=True)
class _Snapshot:
    employees: list
    teams: list
    positions: list
    tasks: list
    approvals: list
    agents: list
    packages: list
    definitions: list
    messages_total: int


class OverviewQuery:
    def __init__(
        self, uow_factory: Callable[[], ReadUnitOfWork], clock: Clock
    ) -> None:
        self._uow = uow_factory
        self._clock = clock

    def get(self) -> OverviewView:
        now = self._clock.now()
        return _overview(self._snapshot(), now)

    def _snapshot(self) -> _Snapshot:
        with self._uow() as uow:
            return _Snapshot(
                employees=uow.employees.list_all(),
                teams=uow.teams.list_all(),
                positions=uow.positions.list_all(),
                tasks=uow.tasks.list_all(),
                approvals=uow.approvals.list_all(ApprovalStatus.PENDING),
                agents=uow.agents.list_all(),
                packages=uow.packages.list_all(),
                definitions=uow.definitions.list_all(),
                messages_total=uow.messages.count(),
            )


def _overview(snapshot: _Snapshot, now: datetime) -> OverviewView:
    employees = _employee_counts(snapshot.employees)
    agents = _agent_counts(snapshot)
    tasks = _task_counts(snapshot.tasks, now)
    skills_total = len(snapshot.packages)
    skills_enabled = sum(1 for item in snapshot.packages if item.enabled)
    workflows_total = len(snapshot.definitions)
    workflows_published = sum(
        1 for item in snapshot.definitions if item.published_version is not None
    )
    return OverviewView(
        employees_total=employees["total"],
        employees_active=employees["active"],
        employees_pending=employees["pending"],
        employees_offline=employees["offline"],
        agents_total=agents["total"],
        agents_enabled=agents["enabled"],
        agents_online=agents["online"],
        agents_busy=agents["busy"],
        teams=len(snapshot.teams),
        positions=len(snapshot.positions),
        seats_occupied=employees["seats_occupied"],
        tasks_total=tasks["total"],
        tasks_active=tasks["active"],
        tasks_running=tasks["running"],
        tasks_blocked=tasks["blocked"],
        tasks_done=tasks["done"],
        tasks_failed_today=tasks["failed_today"],
        approvals_pending=len(snapshot.approvals),
        messages_total=snapshot.messages_total,
        skills_total=skills_total,
        skills_enabled=skills_enabled,
        workflows_total=workflows_total,
        workflows_published=workflows_published,
        metrics=(
            MetricPoint("tasks.active", tasks["active"]),
            MetricPoint("tasks.failed_today", tasks["failed_today"]),
            MetricPoint("bus.messages_total", snapshot.messages_total),
            MetricPoint("agents.online", agents["online"]),
            MetricPoint("agents.total", agents["total"]),
            MetricPoint("humanqueue.pending", len(snapshot.approvals)),
            MetricPoint("skills.total", skills_total),
            MetricPoint("workflows.total", workflows_total),
        ),
    )


def _employee_counts(employees: list) -> dict[str, int]:
    return {
        "total": len(employees),
        "active": sum(
            1 for item in employees if item.status is EmployeeStatus.ACTIVE
        ),
        "pending": sum(
            1 for item in employees if item.status is EmployeeStatus.PENDING
        ),
        "offline": sum(
            1 for item in employees if item.status is EmployeeStatus.OFFLINE
        ),
        "seats_occupied": sum(
            1
            for item in employees
            if item.seat_id and item.status is not EmployeeStatus.DEREGISTERED
        ),
    }


def _agent_counts(snapshot: _Snapshot) -> dict[str, int]:
    enabled = {item.agent_id for item in snapshot.agents if item.enabled}
    bound_active = [
        item
        for item in snapshot.employees
        if item.agent_id in enabled and item.status is EmployeeStatus.ACTIVE
    ]
    busy = {
        item.agent_id
        for item in bound_active
        if any(
            task.owner_id == item.employee_id
            and task.state in _ACTIVE_TASK_STATES
            for task in snapshot.tasks
        )
    }
    return {
        "total": len(snapshot.agents),
        "enabled": len(enabled),
        "online": len(bound_active),
        "busy": len(busy),
    }


def _task_counts(tasks: list, now: datetime) -> dict[str, int]:
    failed_today = sum(
        1
        for item in tasks
        if item.state is TaskState.FAILED
        and item.updated_at is not None
        and item.updated_at.date() == now.date()
    )
    return {
        "total": len(tasks),
        "active": sum(1 for item in tasks if item.state in _ACTIVE_TASK_STATES),
        "running": sum(1 for item in tasks if item.state is TaskState.RUNNING),
        "blocked": sum(1 for item in tasks if item.state is TaskState.BLOCKED),
        "done": sum(1 for item in tasks if item.state is TaskState.DONE),
        "failed_today": failed_today,
    }
