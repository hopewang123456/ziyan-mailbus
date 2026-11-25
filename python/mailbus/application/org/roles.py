"""角色用例：CRUD 与岗位/员工双向绑定。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from mailbus.application.identity.dto import Actor
from mailbus.application.org.admin_ports import OrgAdminUnitOfWork
from mailbus.application.org.dto import RoleView, role_view
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.org.models import Role
from mailbus.core.shared.errors import InvalidStateError, NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class RoleService:
    def __init__(
        self,
        uow_factory: Callable[[], OrgAdminUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def list(self, limit: int, offset: int) -> tuple[list[RoleView], int]:
        with self._uow() as uow:
            roles = uow.roles.list_all()
        return [role_view(item) for item in roles[offset : offset + limit]], len(roles)

    def create(self, actor: Actor, data: dict[str, object]) -> RoleView:
        now = self._clock.now()
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ROLE_MANAGE, Resource(kind="role"))
            role = self._role_from(self._ids.new("role"), data, now)
            uow.roles.add(role)
            uow.commit()
        return role_view(role)

    def update(self, actor: Actor, role_id: str, data: dict[str, object]) -> RoleView:
        now = self._clock.now()
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ROLE_MANAGE, Resource(kind="role"))
            role = self._role(uow, role_id)
            updated = replace(
                self._role_from(role_id, data, now), created_at=role.created_at
            )
            uow.roles.update(updated)
            uow.commit()
        return role_view(updated)

    def delete(self, actor: Actor, role_id: str) -> None:
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ROLE_MANAGE, Resource(kind="role"))
            self._role(uow, role_id)
            if uow.roles.employee_ids(role_id) or uow.roles.position_ids(role_id):
                raise InvalidStateError("角色仍被员工或岗位引用，请先解除绑定")
            uow.roles.delete(role_id)
            uow.commit()

    def bind_positions(
        self, actor: Actor, role_id: str, position_ids: list[str]
    ) -> RoleView:
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ROLE_BIND, Resource(kind="role"))
            role = self._role(uow, role_id)
            for position_id in position_ids:
                if uow.positions.get(position_id) is None:
                    raise NotFoundError("岗位不存在")
            uow.roles.set_positions(role_id, position_ids)
            uow.commit()
        return role_view(role)

    def bind_employees(
        self, actor: Actor, role_id: str, employee_ids: list[str]
    ) -> RoleView:
        with self._uow() as uow:
            ensure_allowed(actor.to_subject(), Capability.ROLE_BIND, Resource(kind="role"))
            role = self._role(uow, role_id)
            existing = {item.employee_id for item in uow.employees.list_all()}
            if any(employee_id not in existing for employee_id in employee_ids):
                raise NotFoundError("存在无效员工")
            uow.roles.set_employees(role_id, employee_ids)
            uow.commit()
        return role_view(role)

    def _role(self, uow: OrgAdminUnitOfWork, role_id: str) -> Role:
        role = uow.roles.get(role_id)
        if role is None:
            raise NotFoundError("角色不存在")
        return role

    @staticmethod
    def _role_from(role_id: str, data: dict[str, object], now: datetime) -> Role:
        return Role(
            role_id=role_id,
            name=str(data["name"]),
            capabilities=frozenset(
                value.strip() for value in data.get("capabilities", []) if value.strip()
            ),
            description=data.get("description"),
            enabled=bool(data.get("enabled", True)),
            icon=data.get("icon"),
            color=data.get("color"),
            created_at=now,
            updated_at=now,
        )
