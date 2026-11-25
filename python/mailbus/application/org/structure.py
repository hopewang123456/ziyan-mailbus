"""组织结构用例：团队、岗位、角色与工位分配。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.org.admin_ports import OrgAdminUnitOfWork
from mailbus.application.org.dto import (
    ContractSeatView,
    PositionView,
    TeamView,
    position_view,
    team_view,
)
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.org import rules
from mailbus.core.org.models import Role, SeatAssignment
from mailbus.core.org.ports import LayoutSeedPort
from mailbus.core.shared.errors import InvalidStateError, NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class StructureService:
    def __init__(
        self,
        uow_factory: Callable[[], OrgAdminUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        seed: LayoutSeedPort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._seed = seed

    # ---------- 团队 ----------

    def list_teams(self, limit: int, offset: int) -> tuple[list[TeamView], int]:
        with self._uow() as uow:
            teams = uow.teams.list_all()
        return [team_view(item) for item in teams[offset : offset + limit]], len(teams)

    def create_team(
        self, actor: Actor, name: str, leader_employee_id: str | None
    ) -> TeamView:
        now = self._clock.now()
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="team"))
            self._ensure_employee(uow, leader_employee_id)
            team, events = rules.create_team(
                self._ids.new("team"), name, now, leader_employee_id
            )
            uow.teams.create(team)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return team_view(team)

    def update_team(
        self, actor: Actor, team_id: str, name: str, leader_employee_id: str | None
    ) -> TeamView:
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="team"))
            team = uow.teams.get(team_id)
            if team is None:
                raise NotFoundError("团队不存在")
            self._ensure_employee(uow, leader_employee_id)
            updated = replace(team, name=name, leader_employee_id=leader_employee_id)
            uow.teams.update(updated)
            uow.commit()
        return team_view(updated)

    def delete_team(self, actor: Actor, team_id: str) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="team"))
            team = uow.teams.get(team_id)
            if team is None:
                raise NotFoundError("团队不存在")
            if any(seat.team_id == team_id for seat in uow.seats.list_all()):
                raise InvalidStateError("团队仍被工位引用，请先解除工位归属")
            if any(
                item.team_id == team_id and item.status is not EmployeeStatus.DEREGISTERED
                for item in uow.employees.list_all()
            ):
                raise InvalidStateError("团队仍被员工引用，请先调整员工归属")
            uow.employees.clear_team_reference(team_id)
            uow.teams.delete(team_id)
            enqueue_events(uow.outbox, rules.delete_team(team, now), self._ids, now)
            uow.commit()

    # ---------- 岗位 ----------

    def list_positions(self, limit: int, offset: int) -> tuple[list[PositionView], int]:
        with self._uow() as uow:
            positions = uow.positions.list_all()
            views = [
                position_view(item, tuple(uow.roles.role_ids_for_position(item.position_id)))
                for item in positions
            ]
        return views[offset : offset + limit], len(views)

    def get_position(self, position_id: str) -> PositionView:
        with self._uow() as uow:
            position = uow.positions.get(position_id)
            if position is None:
                raise NotFoundError("岗位不存在")
            return position_view(
                position, tuple(uow.roles.role_ids_for_position(position_id))
            )

    def create_position(
        self, actor: Actor, name: str, capabilities: list[str]
    ) -> PositionView:
        now = self._clock.now()
        with self._uow() as uow:
            ensure_allowed(
                actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="position")
            )
            position, events = rules.create_position(
                self._ids.new("pos"), name, frozenset(self._skills(capabilities)), now
            )
            uow.positions.add(position)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return position_view(position)

    def update_position(
        self, actor: Actor, position_id: str, name: str, capabilities: list[str]
    ) -> PositionView:
        with self._uow() as uow:
            ensure_allowed(
                actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="position")
            )
            position = uow.positions.get(position_id)
            if position is None:
                raise NotFoundError("岗位不存在")
            updated = replace(
                position, name=name, capabilities=frozenset(self._skills(capabilities))
            )
            uow.positions.update(updated)
            uow.commit()
        return position_view(updated)

    def delete_position(self, actor: Actor, position_id: str) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            ensure_allowed(
                actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="position")
            )
            position = uow.positions.get(position_id)
            if position is None:
                raise NotFoundError("岗位不存在")
            if any(seat.position_id == position_id for seat in uow.seats.list_all()):
                raise InvalidStateError("岗位仍被工位引用，请先解除工位归属")
            if any(
                item.position_id == position_id
                and item.status is not EmployeeStatus.DEREGISTERED
                for item in uow.employees.list_all()
            ):
                raise InvalidStateError("岗位仍被员工引用，请先调整员工归属")
            uow.employees.clear_position_reference(position_id)
            uow.positions.delete(position_id)
            enqueue_events(
                uow.outbox, rules.delete_position(position, now), self._ids, now
            )
            uow.commit()

    def bind_position_roles(
        self, actor: Actor, position_id: str, role_ids: list[str]
    ) -> PositionView:
        with self._uow() as uow:
            ensure_allowed(
                actor.to_subject(), Capability.ROLE_BIND, Resource(kind="position")
            )
            position = self._position(uow, position_id)
            self._ensure_roles(uow, role_ids)
            uow.roles.set_roles_for_position(position_id, role_ids)
            uow.commit()
        return position_view(
            position, tuple(dict.fromkeys(role_ids))
        )

    def bind_position_employees(
        self, actor: Actor, position_id: str, employee_ids: list[str]
    ) -> PositionView:
        now = self._clock.now()
        with self._uow() as uow:
            ensure_allowed(
                actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="position")
            )
            position = self._position(uow, position_id)
            targets = {item.employee_id: item for item in uow.employees.list_all()}
            for employee_id in employee_ids:
                if employee_id not in targets:
                    raise NotFoundError(f"员工不存在：{employee_id}")
            keep = set(employee_ids)
            for employee in targets.values():
                if employee.position_id == position_id and employee.employee_id not in keep:
                    uow.employees.save(replace(employee, position_id=None))
            for employee_id in keep:
                uow.employees.save(
                    replace(
                        targets[employee_id],
                        position_id=position_id,
                        skills=position.capabilities,
                    )
                )
            role_ids = tuple(uow.roles.role_ids_for_position(position_id))
            uow.commit()
        return position_view(position, role_ids)

    # ---------- 工位 ----------

    def list_team_seats(self, actor: Actor, team_id: str) -> list[ContractSeatView]:
        seed = self._seed.load()
        with self._uow() as uow:
            if uow.teams.get(team_id) is None:
                raise NotFoundError("团队不存在")
            overrides = {item.seat_id: item for item in uow.seats.list_all()}
            occupants = {
                item.seat_id: item
                for item in uow.employees.list_all()
                if item.seat_id is not None
            }
        views: list[ContractSeatView] = []
        for floor in seed.floors:
            for room in floor.rooms:
                for seat in room.seats:
                    assignment = overrides.get(seat.seat_id)
                    effective_team = assignment.team_id if assignment else None
                    if effective_team != team_id:
                        continue
                    occupant = occupants.get(seat.seat_id)
                    views.append(
                        self._seat_view(seat.seat_id, seat.x, seat.y, seat.rotation,
                                        assignment, occupant)
                    )
        return views

    def assign_seat(
        self,
        actor: Actor,
        seat_id: str,
        employee_id: str | None,
        team_id: str | None,
        position_id: str | None,
    ) -> ContractSeatView:
        seed = self._seed.load()
        seat = seed.seat_index().get(seat_id)
        if seat is None:
            raise NotFoundError("工位不存在")
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="seat"))
            if team_id is not None and uow.teams.get(team_id) is None:
                raise NotFoundError("团队不存在")
            if position_id is not None and uow.positions.get(position_id) is None:
                raise NotFoundError("岗位不存在")
            previous = uow.seats.get(seat_id)
            assignment = SeatAssignment(
                seat_id=seat_id,
                team_id=team_id,
                position_id=position_id,
                x=previous.x if previous else None,
                y=previous.y if previous else None,
                rotation=previous.rotation if previous else None,
            )
            occupant = self._assign_occupant(uow, seat_id, employee_id)
            uow.seats.upsert(assignment)
            uow.commit()
        return self._seat_view(seat.seat_id, seat.x, seat.y, seat.rotation, assignment, occupant)

    def _assign_occupant(self, uow, seat_id: str, employee_id: str | None):
        current = next(
            (item for item in uow.employees.list_all() if item.seat_id == seat_id),
            None,
        )
        if employee_id is None:
            if current is not None:
                uow.employees.save(replace(current, seat_id=None))
            return None
        target = uow.employees.get(employee_id)
        if target is None:
            raise NotFoundError("员工不存在")
        if current is not None and current.employee_id != employee_id:
            raise InvalidStateError("工位已被占用")
        updated = replace(target, seat_id=seat_id)
        uow.employees.save(updated)
        return updated

    @staticmethod
    def _seat_view(seat_id, x, y, rotation, assignment, occupant) -> ContractSeatView:
        return ContractSeatView(
            seat_id=seat_id,
            team_id=assignment.team_id if assignment else None,
            position_id=assignment.position_id if assignment else None,
            employee_id=occupant.employee_id if occupant else None,
            agent_id=occupant.agent_id if occupant else None,
            x=assignment.x if assignment and assignment.x is not None else x,
            y=assignment.y if assignment and assignment.y is not None else y,
            rotation=(
                assignment.rotation
                if assignment and assignment.rotation is not None
                else rotation
            ),
        )

    # ---------- 辅助 ----------

    def _ensure_employee(self, uow: OrgAdminUnitOfWork, employee_id: str | None) -> None:
        if employee_id is not None and uow.employees.get(employee_id) is None:
            raise NotFoundError("员工不存在")

    def _ensure_roles(self, uow: OrgAdminUnitOfWork, role_ids: list[str]) -> None:
        for role_id in dict.fromkeys(role_ids):
            self._role(uow, role_id)

    def _role(self, uow: OrgAdminUnitOfWork, role_id: str) -> Role:
        role = uow.roles.get(role_id)
        if role is None:
            raise NotFoundError("角色不存在")
        return role

    def _position(self, uow: OrgAdminUnitOfWork, position_id: str):
        position = uow.positions.get(position_id)
        if position is None:
            raise NotFoundError("岗位不存在")
        return position

    @staticmethod
    def _skills(values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in dict.fromkeys(values) if value.strip()]
        if any(len(value) > 64 for value in cleaned):
            raise InvalidStateError("业务技能标签不能超过 64 个字符")
        return cleaned

