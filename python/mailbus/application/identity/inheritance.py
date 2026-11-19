"""岗位能力继承：按入职工位或邀请岗位补齐能力，只增不减。"""

from __future__ import annotations

from datetime import datetime

from mailbus.core.identity import rules
from mailbus.core.identity.models import Employee
from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.shared.events import DomainEvent
from mailbus.core.shared.values import Capability


def inherited_capabilities(
    uow: IdentityUnitOfWork,
    position_id: str | None,
    capabilities: frozenset[Capability],
) -> frozenset[Capability]:
    if not position_id:
        return capabilities
    position = uow.positions.get(position_id)
    return capabilities | (position.capabilities if position else frozenset())


def seat_capabilities(
    uow: IdentityUnitOfWork, seat_id: str | None
) -> frozenset[Capability]:
    if not seat_id:
        return frozenset()
    assignment = uow.seats.get(seat_id)
    if assignment is None or not assignment.position_id:
        return frozenset()
    return inherited_capabilities(uow, assignment.position_id, frozenset())


def inherit_from_seat(
    uow: IdentityUnitOfWork,
    employee: Employee,
    seat_id: str | None,
    now: datetime,
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    if not seat_id:
        return employee, ()
    return rules.inherit_capabilities(employee, seat_capabilities(uow, seat_id), now)
