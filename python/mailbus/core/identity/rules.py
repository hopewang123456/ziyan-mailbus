"""员工生命周期的纯函数状态转移。

每个函数返回 (新状态, 领域事件)，不落库、不生成 id、不读时钟。
非法转移抛领域异常；application 负责事务、仓储与事件投递。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mailbus.core.identity.models import Employee, Registration
from mailbus.core.identity.values import MANAGER_CAPABILITIES, EmployeeStatus
from mailbus.core.shared.errors import InvalidStateError, InvalidTransitionError
from mailbus.core.shared.events import DomainEvent
from mailbus.core.shared.values import Capability


def _event(kind: str, **payload: object) -> DomainEvent:
    return DomainEvent(kind=kind, payload=dict(payload))


def submit(reg: Registration, now: datetime) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """提交申请：生成 pending 员工（邀请核准的申请直接带 approved_at）。"""
    employee = Employee(
        employee_id=reg.employee_id,
        display_name=reg.display_name,
        account_type=reg.account_type,
        status=EmployeeStatus.PENDING,
        team_id=reg.team_id,
        position_id=reg.position_id,
        seat_id=reg.seat_id,
        capabilities=reg.capabilities,
        data_scope=reg.data_scope,
        file_scope=reg.file_scope,
        endpoint=reg.endpoint,
        approved_at=now if reg.approved else None,
        agent_id=reg.agent_id,
    )
    event = _event(
        "identity.application_submitted",
        employee_id=employee.employee_id,
        account_type=employee.account_type.value,
        at=now.isoformat(),
    )
    return employee, (event,)


def review(
    employee: Employee,
    *,
    approved: bool,
    reviewer_id: str,
    now: datetime,
    note: str | None = None,
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """审核申请：通过只记录核准时间，激活由 activate 单独完成；驳回即注销。"""
    if employee.status is not EmployeeStatus.PENDING:
        raise InvalidTransitionError("只有待审核申请可以审核")
    if employee.approved_at is not None:
        raise InvalidStateError("申请已通过审核，请直接激活")
    payload = {
        "employee_id": employee.employee_id,
        "reviewer_id": reviewer_id,
        "note": note or "",
        "at": now.isoformat(),
    }
    if not approved:
        rejected = replace(employee, status=EmployeeStatus.DEREGISTERED)
        return rejected, (_event("identity.application_rejected", **payload),)
    return replace(employee, approved_at=now), (_event("identity.application_approved", **payload),)


def activate(employee: Employee, now: datetime) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """激活：pending 且已核准 → active。"""
    if employee.status is not EmployeeStatus.PENDING:
        raise InvalidTransitionError("只有待激活账号可以激活")
    if employee.approved_at is None:
        raise InvalidTransitionError("申请尚未通过审核")
    activated = replace(employee, status=EmployeeStatus.ACTIVE, last_heartbeat=now)
    event = _event(
        "identity.employee_activated",
        employee_id=employee.employee_id,
        at=now.isoformat(),
    )
    return activated, (event,)


def heartbeat(employee: Employee, now: datetime) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """心跳：active/offline 均可；仅从 offline 恢复时产生上线事件。"""
    if employee.status is EmployeeStatus.PENDING:
        raise InvalidTransitionError("账号尚未激活")
    if employee.status is EmployeeStatus.DEREGISTERED:
        raise InvalidTransitionError("账号已注销")
    revived = employee.status is EmployeeStatus.OFFLINE
    updated = replace(employee, status=EmployeeStatus.ACTIVE, last_heartbeat=now)
    if not revived:
        return updated, ()
    event = _event(
        "identity.employee_online",
        employee_id=employee.employee_id,
        at=now.isoformat(),
    )
    return updated, (event,)


def assign_seat(
    employee: Employee, seat_id: str | None, now: datetime
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """分配/释放工位；注销员工不再参与座位调整。"""
    if employee.status is EmployeeStatus.DEREGISTERED:
        raise InvalidStateError("已注销员工不能分配工位")
    if employee.seat_id == seat_id:
        return employee, ()
    assigned = replace(employee, seat_id=seat_id)
    event = _event(
        "identity.seat_assigned",
        employee_id=employee.employee_id,
        seat_id=seat_id or "",
        at=now.isoformat(),
    )
    return assigned, (event,)


def inherit_capabilities(
    employee: Employee, extra: frozenset[Capability], now: datetime
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """按岗位补齐能力：只增不减，已授予的能力保持不变。"""
    merged = employee.capabilities | extra
    if merged == employee.capabilities:
        return employee, ()
    updated = replace(employee, capabilities=frozenset(merged))
    event = _event(
        "identity.capabilities_inherited",
        employee_id=employee.employee_id,
        added=sorted(cap.value for cap in merged - employee.capabilities),
        at=now.isoformat(),
    )
    return updated, (event,)


def set_agent(
    employee: Employee, agent_id: str | None, now: datetime
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """绑定/解绑 Agent；已注销员工不再允许变更。"""
    if employee.status is EmployeeStatus.DEREGISTERED:
        raise InvalidStateError("已注销员工不能绑定 Agent")
    if employee.agent_id == agent_id:
        return employee, ()
    updated = replace(employee, agent_id=agent_id)
    event = _event(
        "identity.agent_bound",
        employee_id=employee.employee_id,
        agent_id=agent_id or "",
        at=now.isoformat(),
    )
    return updated, (event,)


def set_endpoint_approved(
    employee: Employee, approved: bool, now: datetime
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """Agent 端点审核：通过前必须有登记端点。"""
    if approved and not employee.endpoint:
        raise InvalidStateError("员工尚未登记端点，无法通过审核")
    if employee.endpoint_approved == approved:
        return employee, ()
    updated = replace(employee, endpoint_approved=approved)
    event = _event(
        "identity.endpoint_reviewed",
        employee_id=employee.employee_id,
        approved=approved,
        at=now.isoformat(),
    )
    return updated, (event,)


def set_manager(
    employee: Employee, enabled: bool, now: datetime
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """指定/取消管理者：启用并集能力包，停用只移除 CONSOLE_ADMIN。"""
    if employee.status is EmployeeStatus.DEREGISTERED:
        raise InvalidStateError("已注销员工不能设为管理者")
    if enabled:
        capabilities = employee.capabilities | MANAGER_CAPABILITIES
    else:
        capabilities = employee.capabilities - {Capability.CONSOLE_ADMIN}
    if capabilities == employee.capabilities:
        return employee, ()
    updated = replace(employee, capabilities=frozenset(capabilities))
    event = _event(
        "identity.manager_changed",
        employee_id=employee.employee_id,
        enabled=enabled,
        at=now.isoformat(),
    )
    return updated, (event,)


def mark_offline(employee: Employee, now: datetime) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """心跳超时：只允许 active → offline。"""
    if employee.status is not EmployeeStatus.ACTIVE:
        raise InvalidTransitionError("只有在线账号可以标记离线")
    offline = replace(employee, status=EmployeeStatus.OFFLINE)
    event = _event(
        "identity.employee_offline",
        employee_id=employee.employee_id,
        at=now.isoformat(),
    )
    return offline, (event,)


def deregister(
    employee: Employee, *, reason: str, actor_id: str, now: datetime
) -> tuple[Employee, tuple[DomainEvent, ...]]:
    """注销：幂等；离职即自动释放工位，工位可被重新分配。"""
    if employee.status is EmployeeStatus.DEREGISTERED:
        return employee, ()
    dismissed = replace(
        employee,
        status=EmployeeStatus.DEREGISTERED,
        seat_id=None,
    )
    event = _event(
        "identity.employee_deregistered",
        employee_id=employee.employee_id,
        actor_id=actor_id,
        reason=reason,
        released_seat_id=employee.seat_id or "",
        at=now.isoformat(),
    )
    return dismissed, (event,)
