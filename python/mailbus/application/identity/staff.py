"""员工用例：心跳、离线巡检与查询。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from mailbus.application.identity.dto import (
    Actor,
    EmployeeView,
    OccupantView,
    employee_view,
)
from mailbus.application.events import enqueue_events
from mailbus.application.identity import scoping
from mailbus.core.agents.models import AgentSummary
from mailbus.core.agents.ports import AgentDirectoryPort
from mailbus.core.identity import rules
from mailbus.core.identity.models import Employee
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.identity.values import ON_DUTY_STATUSES, EmployeeStatus
from mailbus.core.shared.errors import NotFoundError, PermissionDeniedError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class StaffService:
    def __init__(
        self,
        uow_factory: Callable[[], IdentityUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        agents: AgentDirectoryPort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._agents = agents

    def heartbeat(self, actor: Actor, employee_id: str) -> EmployeeView:
        if actor.employee_id != employee_id and Capability.ALL not in actor.capabilities:
            raise PermissionDeniedError("只能上报自己的心跳")
        now = self._clock.now()
        with self._uow() as uow:
            updated, events = rules.heartbeat(self._load(uow, employee_id), now)
            uow.employees.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(updated)

    def seat_of(self, employee_id: str) -> str:
        """内部查询：员工当前工位；无工位或员工不存在返回空串，供公开事件定位。"""
        with self._uow() as uow:
            employee = uow.employees.get(employee_id)
        return (employee.seat_id or "") if employee is not None else ""

    def mark_stale_offline(self, cutoff: datetime) -> int:
        """心跳超时扫描：active 且最后心跳早于 cutoff 的员工置为 offline。"""
        now = self._clock.now()
        offline = 0
        with self._uow() as uow:
            for employee in uow.employees.list_stale_active(cutoff):
                updated, events = rules.mark_offline(employee, now)
                uow.employees.save(updated)
                enqueue_events(uow.outbox, events, self._ids, now)
                offline += 1
            if offline:
                uow.commit()
        return offline

    def list_staff(self, actor: Actor, status: str = "pending") -> tuple[EmployeeView, ...]:
        """员工列表：pending 仅待审，active 含离线，all 不做状态过滤。"""
        ensure_allowed(
            actor.to_subject(), Capability.EMPLOYEE_INVITE, Resource(kind="employee")
        )
        with self._uow() as uow:
            employees = uow.employees.list_all()
        employees = scoping.filter_by_scope(actor, employees)
        if status == "pending":
            employees = [
                employee
                for employee in employees
                if employee.status is EmployeeStatus.PENDING
            ]
        elif status == "active":
            employees = [
                employee
                for employee in employees
                if employee.status in ON_DUTY_STATUSES
            ]
        summaries = self._agent_summaries(employees)
        return tuple(
            employee_view(employee, summaries.get(employee.agent_id or ""))
            for employee in employees
        )

    def me(self, actor: Actor) -> EmployeeView:
        with self._uow() as uow:
            employee = self._load(uow, actor.employee_id)
        return self._view(employee)

    def get(self, actor: Actor, employee_id: str) -> EmployeeView:
        """员工详情：本人或具备邀请/管理能力者可读。"""
        with self._uow() as uow:
            employee = self._load(uow, employee_id)
        if actor.employee_id != employee_id:
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="employee", team_id=employee.team_id),
            )
        return self._view(employee)

    def occupants(self) -> tuple[OccupantView, ...]:
        """布局投影用：只返回座位与在线状态，不暴露能力等敏感字段。"""
        with self._uow() as uow:
            employees = uow.employees.list_all()
        return tuple(
            OccupantView(
                employee_id=employee.employee_id,
                display_name=employee.display_name,
                team_id=employee.team_id,
                position_id=employee.position_id,
                seat_id=employee.seat_id,
                agent_id=employee.agent_id,
                status=employee.status.value,
                last_heartbeat=employee.last_heartbeat,
            )
            for employee in employees
            if employee.status is not EmployeeStatus.DEREGISTERED
        )

    def _view(
        self, employee: Employee, summary: AgentSummary | None = None
    ) -> EmployeeView:
        if summary is None and employee.agent_id:
            summary = self._agents.summaries((employee.agent_id,)).get(employee.agent_id)
        return employee_view(employee, summary)

    def _agent_summaries(
        self, employees: list[Employee]
    ) -> dict[str, AgentSummary]:
        return self._agents.summaries(
            tuple(employee.agent_id for employee in employees if employee.agent_id)
        )

    def _load(self, uow: IdentityUnitOfWork, employee_id: str) -> Employee:
        employee = uow.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("员工不存在")
        return employee
