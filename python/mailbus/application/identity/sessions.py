"""会话签发与解析。

token 只以哈希形式落库；解析结果转换为 Actor 供用例做权限判定。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from mailbus.application.identity.dto import Actor
from mailbus.core.identity.models import Employee
from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.shared.errors import AuthenticationError
from mailbus.core.shared.ports import Clock, IdGenerator

SESSION_TTL = timedelta(days=7)


def issue_session(
    uow: IdentityUnitOfWork,
    employee: Employee,
    ids: IdGenerator,
    now: datetime,
    ttl: timedelta | None = SESSION_TTL,
) -> str:
    """签发会话；ttl 为 None 表示永久（expires_at 落库为空）。"""
    token = ids.new("mbk")
    uow.sessions.issue(employee.employee_id, token, now, None if ttl is None else now + ttl)
    return token


class SessionService:
    def __init__(
        self,
        uow_factory: Callable[[], IdentityUnitOfWork],
        clock: Clock,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock

    def resolve(self, token: str) -> Actor:
        now = self._clock.now()
        with self._uow() as uow:
            employee_id = uow.sessions.resolve(token, now)
            employee = uow.employees.get(employee_id) if employee_id else None
        if employee is None or employee.status is EmployeeStatus.DEREGISTERED:
            raise AuthenticationError("登录凭证无效或已过期")
        return Actor.of(employee)

    def logout(self, token: str) -> None:
        now = self._clock.now()
        with self._uow() as uow:
            uow.sessions.revoke(token, now)
            uow.commit()
