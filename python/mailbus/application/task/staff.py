"""派活候选与认领资格：岗位 → 角色 → 技能交集。"""

from __future__ import annotations

from datetime import datetime, timezone

from mailbus.core.agents import rules as agent_rules
from mailbus.core.identity.models import Employee
from mailbus.core.identity.values import AccountType, ON_DUTY_STATUSES
from mailbus.core.workflow.models import WorkflowNode


def pick_candidates(
    uow, wf: WorkflowNode, account_type: AccountType, now: datetime | None = None
) -> list[Employee]:
    required = _required_skills(uow, wf)
    role_ids = _role_ids(uow, wf)
    moment = now or datetime.now(timezone.utc)
    candidates: list[Employee] = []
    for employee in uow.employees.list_all():
        if employee.account_type is not account_type:
            continue
        if employee.status not in ON_DUTY_STATUSES:
            continue
        if employee.deleted_at is not None:
            continue
        if not _position_match(uow, employee, wf, role_ids):
            continue
        if required and not (employee.skills & required):
            continue
        if not _agent_dispatchable(uow, employee, moment):
            continue
        candidates.append(employee)
    return sorted(
        candidates,
        key=lambda item: (uow.runs.count_active_by_employee(item.employee_id), item.employee_id),
    )


def can_claim(uow, employee: Employee, wf: WorkflowNode | None) -> bool:
    if employee.account_type is not AccountType.HUMAN:
        return False
    if employee.status not in ON_DUTY_STATUSES or employee.deleted_at is not None:
        return False
    if wf is None or not wf.position_id:
        return True
    return _position_match(uow, employee, wf, _role_ids(uow, wf))


def _agent_dispatchable(uow, employee: Employee, now: datetime) -> bool:
    """Agent 端点待审批/被拒/离线/删除时绝不派单；未登记台账的旧绑定保持兼容。"""
    if employee.account_type is not AccountType.AGENT or not employee.agent_id:
        return True
    agent = uow.agents.get(employee.agent_id)
    if agent is None:
        return True
    return agent_rules.dispatchable(agent, now)


def _required_skills(uow, wf: WorkflowNode) -> frozenset[str]:
    skills: set[str] = set()
    position = uow.positions.get(wf.position_id) if wf.position_id else None
    if position is not None:
        skills |= position.capabilities
    for role_id in _role_ids(uow, wf):
        role = uow.roles.get(role_id)
        if role is not None and role.enabled:
            skills |= role.capabilities
    return frozenset(skills)


def _role_ids(uow, wf: WorkflowNode) -> list[str]:
    if not wf.position_id:
        return []
    return uow.roles.role_ids_for_position(wf.position_id)


def _position_match(uow, employee: Employee, wf: WorkflowNode, role_ids: list[str]) -> bool:
    if not wf.position_id:
        return True
    if employee.position_id == wf.position_id:
        return True
    return bool(set(uow.roles.role_ids_for_employee(employee.employee_id)) & set(role_ids))
