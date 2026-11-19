"""身份上下文对外的仓储端口（由 adapters 实现）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Self

from mailbus.core.identity.models import Employee, Invite
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.org.ports import PositionRepository, SeatRepository
from mailbus.core.shared.ports import OutboxPort


class EmployeeRepository(Protocol):
    def get(self, employee_id: str) -> Employee | None: ...

    def save(self, employee: Employee) -> None:
        """整聚合落库（含能力集合）。"""

    def list_by_status(self, status: EmployeeStatus) -> list[Employee]: ...

    def list_all(self) -> list[Employee]: ...


class InviteRepository(Protocol):
    def add(self, invite: Invite) -> None: ...

    def get(self, invite_code: str) -> Invite | None: ...

    def consume(self, invite_code: str, employee_id: str, at: datetime) -> bool:
        """原子消费；返回 False 表示已被消费。"""


class SessionRepository(Protocol):
    def issue(
        self,
        employee_id: str,
        token: str,
        issued_at: datetime,
        expires_at: datetime | None,
    ) -> None: ...

    def resolve(self, token: str, now: datetime) -> str | None:
        """返回 employee_id；无效、过期或已撤销返回 None。"""

    def revoke(self, token: str, at: datetime) -> None: ...

    def revoke_all(self, employee_id: str, at: datetime) -> None: ...


class BootstrapRepository(Protocol):
    def completed(self) -> dict[str, dict[str, Any]]:
        """step → detail。"""

    def mark(self, step: str, detail: dict[str, Any], at: datetime) -> None: ...


class IdentityUnitOfWork(Protocol):
    """身份用例的事务边界；一个用例一个实例。"""

    outbox: OutboxPort
    employees: EmployeeRepository
    invites: InviteRepository
    sessions: SessionRepository
    bootstrap: BootstrapRepository
    positions: PositionRepository
    seats: SeatRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
