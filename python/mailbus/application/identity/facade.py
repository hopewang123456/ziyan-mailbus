"""身份上下文的应用服务装配。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mailbus.application.identity.bootstrap import BootstrapService
from mailbus.application.identity.sessions import SessionService
from mailbus.application.identity.staff import StaffService
from mailbus.application.org.service import OrgService
from mailbus.core.agents.ports import AgentDirectoryPort
from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.shared.ports import Clock, IdGenerator


@dataclass(frozen=True, slots=True)
class IdentityServices:
    bootstrap: BootstrapService
    staff: StaffService
    sessions: SessionService

    @classmethod
    def create(
        cls,
        uow_factory: Callable[[], IdentityUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        org: OrgService,
        agents: AgentDirectoryPort,
    ) -> "IdentityServices":
        return cls(
            bootstrap=BootstrapService(uow_factory, clock, ids, org),
            staff=StaffService(uow_factory, clock, ids, agents),
            sessions=SessionService(uow_factory, clock),
        )
