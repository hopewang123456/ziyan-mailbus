"""组织管理服务装配：员工目录、组织结构、邀请。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mailbus.application.org.admin_ports import OrgAdminUnitOfWork
from mailbus.application.org.employees import EmployeeAdminService
from mailbus.application.org.invites_admin import InviteAdminService
from mailbus.application.org.roles import RoleService
from mailbus.application.org.structure import StructureService
from mailbus.core.agents.ports import AgentDirectoryPort
from mailbus.core.org.ports import LayoutSeedPort
from mailbus.core.shared.ports import Clock, IdGenerator


@dataclass(frozen=True, slots=True)
class OrgAdminServices:
    employees: EmployeeAdminService
    structure: StructureService
    roles: RoleService
    invites: InviteAdminService

    @classmethod
    def create(
        cls,
        uow_factory: Callable[[], OrgAdminUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        seed: LayoutSeedPort,
        agents: AgentDirectoryPort,
    ) -> "OrgAdminServices":
        return cls(
            employees=EmployeeAdminService(uow_factory, clock, ids, agents, seed),
            structure=StructureService(uow_factory, clock, ids, seed),
            roles=RoleService(uow_factory, clock, ids),
            invites=InviteAdminService(uow_factory, clock, ids),
        )
