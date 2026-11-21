"""可见范围裁剪（纯函数，供列表查询复用）。"""

from __future__ import annotations

from mailbus.application.identity.dto import Actor
from mailbus.core.approval.models import ApprovalItem
from mailbus.core.identity.models import Employee
from mailbus.core.identity.policy import can_read_sensitive as _policy_can_read_sensitive
from mailbus.core.shared.values import Capability, DataScope
from mailbus.core.workflow.models import Task


def can_read_sensitive(actor: Actor) -> bool:
    """api 层可见性判定：是否可见技能来源路径 / Agent 端点等敏感元数据。"""
    return _policy_can_read_sensitive(actor.capabilities)


def can_view_ops_alerts(actor: Actor) -> bool:
    """运维告警（指标超阈值）仅对全局范围或管理端能力可见。"""
    return (
        actor.data_scope is DataScope.GLOBAL
        or Capability.ALL in actor.capabilities
        or Capability.CONSOLE_ADMIN in actor.capabilities
    )


def can_query_any_skills(actor: Actor) -> bool:
    """可查询任意员工/Agent 的有效技能：超管、系统配置或管理端。"""
    return (
        Capability.ALL in actor.capabilities
        or Capability.SYSTEM_CONFIG in actor.capabilities
        or Capability.CONSOLE_ADMIN in actor.capabilities
    )


def filter_by_scope(
    actor: Actor, employees: list[Employee]
) -> list[Employee]:
    """global 全量、team 本队（含本人）、self 仅本人。"""
    if actor.data_scope is DataScope.GLOBAL:
        return list(employees)
    if actor.data_scope is DataScope.TEAM:
        return [
            e
            for e in employees
            if e.team_id == actor.team_id or e.employee_id == actor.employee_id
        ]
    return [e for e in employees if e.employee_id == actor.employee_id]


def filter_approvals_by_scope(
    actor: Actor,
    approvals: list[ApprovalItem],
    tasks: list[Task],
    employees: list[Employee],
) -> list[ApprovalItem]:
    """审批可见范围：global 全量；team 本队任务相关（含本人发起）；self 仅本人发起或归属。"""
    if actor.data_scope is DataScope.GLOBAL:
        return list(approvals)
    task_owner: dict[str, str | None] = {t.task_id: t.owner_id for t in tasks}
    if actor.data_scope is DataScope.TEAM:
        visible_owners = {
            e.employee_id for e in employees if e.team_id == actor.team_id
        }
        visible_owners.add(actor.employee_id)
    else:
        visible_owners = {actor.employee_id}
    result: list[ApprovalItem] = []
    for item in approvals:
        owner = task_owner.get(item.task_id)
        if item.requester_id == actor.employee_id:
            result.append(item)
        elif owner is not None and owner in visible_owners:
            result.append(item)
    return result


def filter_tasks_by_scope(
    actor: Actor, tasks: list[Task], employees: list[Employee]
) -> list[Task]:
    """任务可见范围：global 全量；team 本队（含本人）；self 仅本人归属。"""
    if actor.data_scope is DataScope.GLOBAL:
        return list(tasks)
    if actor.data_scope is DataScope.TEAM:
        team_mates = {
            e.employee_id for e in employees if e.team_id == actor.team_id
        }
        team_mates.add(actor.employee_id)
        return [t for t in tasks if t.owner_id in team_mates]
    return [t for t in tasks if t.owner_id == actor.employee_id]
