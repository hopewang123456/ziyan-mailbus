"""员工目录用例：列表、详情、更新、软删除、权限/角色/技能与脱敏选项。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor, EmployeeView
from mailbus.application.org.admin_ports import OrgAdminUnitOfWork
from mailbus.application.org.dto import OptionView
from mailbus.core.agents.ports import AgentDirectoryPort
from mailbus.core.identity import rules
from mailbus.core.identity.models import Employee
from mailbus.core.identity.policy import (
    Resource,
    ensure_allowed,
    ensure_grantable,
)
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.org.models import Position
from mailbus.core.org.ports import LayoutSeedPort
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    UnprocessableError,
)
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability, DataScope


class EmployeeAdminService:
    def __init__(
        self,
        uow_factory: Callable[[], OrgAdminUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        agents: AgentDirectoryPort,
        seed: LayoutSeedPort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._agents = agents
        self._seed = seed

    def list(
        self,
        actor: Actor,
        account_type: str | None,
        position_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[EmployeeView], int]:
        with self._uow() as uow:
            employees = [
                item
                for item in uow.employees.list_all()
                if (account_type is None or item.account_type.value == account_type)
                and (position_id is None or item.position_id == position_id)
            ]
        total = len(employees)
        page = employees[offset : offset + limit]
        return self._views(page), total

    def get(self, actor: Actor, employee_id: str) -> EmployeeView:
        with self._uow() as uow:
            employee = self._load(uow, employee_id)
        if actor.employee_id != employee_id:
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="employee", team_id=employee.team_id),
            )
        return self._views([employee])[0]

    def update(
        self,
        actor: Actor,
        employee_id: str,
        changes: dict[str, object],
    ) -> EmployeeView:
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.ORG_MANAGE,
                Resource(kind="employee", team_id=target.team_id),
            )
            updated, events = self._apply(uow, actor, target, changes, now)
            uow.employees.save(updated)
            if updated.status is EmployeeStatus.DEREGISTERED:
                uow.sessions.revoke_all(employee_id, now)
            self._enqueue(uow, events, now)
            uow.commit()
        return self._views([updated])[0]

    def delete(self, actor: Actor, employee_id: str) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_REMOVE,
                Resource(
                    kind="employee",
                    team_id=target.team_id,
                    owner_id=target.employee_id,
                ),
            )
            if uow.employees.active_run_count(employee_id) > 0:
                raise InvalidStateError("员工仍有进行中的任务，不能移除")
            uow.employees.soft_delete(employee_id, actor.employee_id, now)
            uow.sessions.revoke_all(employee_id, now)
            uow.commit()

    def permissions(self, actor: Actor, employee_id: str) -> tuple[str, ...]:
        with self._uow() as uow:
            employee = self._load(uow, employee_id)
        return tuple(sorted(cap.value for cap in employee.capabilities))

    def set_permissions(
        self, actor: Actor, employee_id: str, values: list[str]
    ) -> tuple[str, ...]:
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.CONSOLE_ADMIN,
                Resource(kind="employee", team_id=target.team_id),
            )
            requested = self._capabilities(values)
            ensure_grantable(
                actor.capabilities, actor.data_scope, requested, target.data_scope
            )
            updated = replace(target, capabilities=requested)
            uow.employees.save(updated)
            uow.commit()
        return tuple(sorted(cap.value for cap in requested))

    def roles(self, actor: Actor, employee_id: str) -> tuple[str, ...]:
        with self._uow() as uow:
            self._load(uow, employee_id)
            return tuple(uow.roles.role_ids_for_employee(employee_id))

    def set_roles(
        self, actor: Actor, employee_id: str, role_ids: list[str]
    ) -> tuple[str, ...]:
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.ROLE_BIND,
                Resource(kind="employee", team_id=target.team_id),
            )
            self._ensure_roles(uow, role_ids)
            uow.roles.set_roles_for_employee(employee_id, role_ids)
            uow.commit()
            return tuple(uow.roles.role_ids_for_employee(employee_id))

    def capabilities(self, actor: Actor, employee_id: str) -> tuple[str, ...]:
        with self._uow() as uow:
            employee = self._load(uow, employee_id)
        return tuple(sorted(employee.skills))

    def set_capabilities(
        self, actor: Actor, employee_id: str, values: list[str]
    ) -> tuple[str, ...]:
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.ROLE_BIND,
                Resource(kind="employee", team_id=target.team_id),
            )
            skills = frozenset(self._skills(values))
            uow.employees.save(replace(target, skills=skills))
            uow.commit()
        return tuple(sorted(skills))

    def options(
        self,
        actor: Actor,
        position_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[OptionView], int]:
        with self._uow() as uow:
            employees = [
                item
                for item in uow.employees.list_all()
                if self._in_scope(actor, item)
                and (position_id is None or item.position_id == position_id)
            ]
        total = len(employees)
        page = employees[offset : offset + limit]
        return [
            OptionView(
                option_id=item.employee_id,
                label=item.display_name,
                enabled=item.status not in (EmployeeStatus.PENDING, EmployeeStatus.DEREGISTERED),
            )
            for item in page
        ], total

    def _apply(
        self,
        uow: OrgAdminUnitOfWork,
        actor: Actor,
        target: Employee,
        changes: dict[str, object],
        now: datetime,
    ) -> tuple[Employee, tuple]:
        if target.status is EmployeeStatus.DEREGISTERED:
            raise InvalidStateError("已注销员工不能修改")
        updated = target
        if changes.get("display_name") is not None:
            updated = replace(updated, display_name=str(changes["display_name"]))
        if "team_id" in changes:
            updated = replace(updated, team_id=self._team(uow, changes["team_id"]))
        if "position_id" in changes:
            updated = self._with_position(uow, updated, changes["position_id"])
        if "seat_id" in changes:
            updated = self._with_seat(uow, updated, changes["seat_id"])
        if changes.get("data_scope") is not None:
            self._ensure_scope(actor, DataScope(str(changes["data_scope"])))
            updated = replace(updated, data_scope=DataScope(str(changes["data_scope"])))
        events: tuple = ()
        if changes.get("enabled") is not None:
            updated, events = self._toggle(updated, bool(changes["enabled"]), actor, now)
        return updated, events

    def _with_position(
        self, uow: OrgAdminUnitOfWork, employee: Employee, value: object
    ) -> Employee:
        position_id = value if value is None else str(value)
        if position_id is None:
            if employee.account_type.value == "agent":
                raise UnprocessableError("Agent 员工必须绑定岗位")
            return replace(employee, position_id=None)
        position = uow.positions.get(position_id)
        if position is None:
            raise NotFoundError("岗位不存在")
        return replace(employee, position_id=position_id, skills=position.capabilities)

    def _with_seat(
        self, uow: OrgAdminUnitOfWork, employee: Employee, value: object
    ) -> Employee:
        seat_id = value if value is None else str(value)
        if seat_id is None:
            return replace(employee, seat_id=None)
        if seat_id not in self._seed.load().seat_index():
            raise NotFoundError("工位不存在")
        occupant = next(
            (
                item
                for item in uow.employees.list_all()
                if item.seat_id == seat_id and item.employee_id != employee.employee_id
            ),
            None,
        )
        if occupant is not None:
            raise InvalidStateError("工位已被占用")
        return replace(employee, seat_id=seat_id)

    def _toggle(
        self, employee: Employee, enabled: bool, actor: Actor, now: datetime
    ) -> tuple[Employee, tuple]:
        if not enabled:
            return rules.deregister(
                employee, reason="管理员停用", actor_id=actor.employee_id, now=now
            )
        if employee.status is EmployeeStatus.DEREGISTERED:
            raise InvalidStateError("已停用员工不能直接启用，请重新邀请")
        if employee.status is EmployeeStatus.PENDING:
            return rules.activate(employee, now)
        return replace(employee, status=EmployeeStatus.ACTIVE), ()

    def _ensure_scope(self, actor: Actor, target: DataScope) -> None:
        ensure_grantable(actor.capabilities, actor.data_scope, frozenset(), target)

    def _team(self, uow: OrgAdminUnitOfWork, value: object) -> str | None:
        if value is None:
            return None
        team = uow.teams.get(str(value))
        if team is None:
            raise NotFoundError("团队不存在")
        return team.team_id

    def _ensure_roles(self, uow: OrgAdminUnitOfWork, role_ids: list[str]) -> None:
        for role_id in dict.fromkeys(role_ids):
            if uow.roles.get(role_id) is None:
                raise NotFoundError(f"角色不存在：{role_id}")

    def _capabilities(self, values: list[str]) -> frozenset[Capability]:
        try:
            return frozenset(Capability(value) for value in dict.fromkeys(values))
        except ValueError as exc:
            raise UnprocessableError("存在未知权限值") from exc

    @staticmethod
    def _skills(values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in dict.fromkeys(values) if value.strip()]
        if any(len(value) > 64 for value in cleaned):
            raise UnprocessableError("业务技能标签不能超过 64 个字符")
        return cleaned

    @staticmethod
    def _in_scope(actor: Actor, employee: Employee) -> bool:
        if actor.data_scope is DataScope.GLOBAL:
            return True
        if actor.data_scope is DataScope.TEAM:
            return actor.team_id is not None and employee.team_id == actor.team_id
        return employee.employee_id == actor.employee_id

    def _load(self, uow: OrgAdminUnitOfWork, employee_id: str) -> Employee:
        employee = uow.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("员工不存在")
        return employee

    def _views(self, employees: list[Employee]) -> list[EmployeeView]:
        agent_ids = tuple(
            item.agent_id for item in employees if item.agent_id is not None
        )
        summaries = self._agents.summaries(agent_ids) if agent_ids else {}
        return [
            EmployeeView.of(employee, summaries.get(employee.agent_id))
            for employee in employees
        ]

    def _enqueue(self, uow: OrgAdminUnitOfWork, events: tuple, now: datetime) -> None:
        if events:
            enqueue_events(uow.outbox, events, self._ids, now)
