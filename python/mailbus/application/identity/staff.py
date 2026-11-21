"""员工用例：申请、审核、激活、心跳、注销。

写用例的第一步都是权限判定；apply 是公开入口，由邀请码或审核兜底。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from mailbus.application.identity.dto import (
    Actor,
    ApplyCommand,
    ApplyResult,
    EmployeeView,
    OccupantView,
    ReviewCommand,
    SessionResult,
    employee_view,
)
from mailbus.application.events import enqueue_events
from mailbus.application.identity import inheritance, scoping
from mailbus.application.identity.sessions import issue_session
from mailbus.core.agents.models import AgentSummary
from mailbus.core.agents.ports import AgentDirectoryPort
from mailbus.core.identity import rules
from mailbus.core.identity.errors import InviteInvalidError
from mailbus.core.identity.models import Employee, Invite, Registration
from mailbus.core.identity.policy import Resource, can_grant_capabilities, ensure_allowed
from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.identity.values import ON_DUTY_STATUSES, EmployeeStatus
from mailbus.core.org.ports import LayoutSeedPort
from mailbus.core.shared.errors import InvalidStateError, NotFoundError, PermissionDeniedError
from mailbus.core.shared.events import DomainEvent
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class StaffService:
    def __init__(
        self,
        uow_factory: Callable[[], IdentityUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        seed: LayoutSeedPort,
        agents: AgentDirectoryPort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._seed = seed
        self._agents = agents

    def apply(self, cmd: ApplyCommand) -> ApplyResult:
        if cmd.agent_id and not self._agents.summaries((cmd.agent_id,)):
            raise NotFoundError("Agent 不存在")
        now = self._clock.now()
        employee_id = self._ids.new("emp")
        with self._uow() as uow:
            employee, events = self._register(uow, cmd, employee_id, now)
            uow.employees.save(employee)
            token = (
                issue_session(uow, employee, self._ids, now)
                if employee.status is EmployeeStatus.ACTIVE
                else None
            )
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return ApplyResult(employee=self._view(employee), token=token)

    def review(self, actor: Actor, employee_id: str, cmd: ReviewCommand) -> EmployeeView:
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="employee", team_id=target.team_id),
            )
            updated, events = rules.review(
                target,
                approved=cmd.approved,
                reviewer_id=actor.employee_id,
                now=now,
                note=cmd.note,
            )
            uow.employees.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(updated)

    def activate(self, actor: Actor, employee_id: str) -> SessionResult:
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="employee", team_id=target.team_id),
            )
            if not can_grant_capabilities(actor.capabilities, target.capabilities):
                raise PermissionDeniedError("不能激活超出自身能力范围的账号")
            updated, events = rules.activate(target, now)
            uow.employees.save(updated)
            token = issue_session(uow, updated, self._ids, now)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return SessionResult(employee=self._view(updated), token=token)

    def heartbeat(self, actor: Actor, employee_id: str) -> EmployeeView:
        # 本人可自报；持全量权限的超管可代任意员工续心跳（演示/运维保活）。
        if actor.employee_id != employee_id and Capability.ALL not in actor.capabilities:
            raise PermissionDeniedError("只能上报自己的心跳")
        now = self._clock.now()
        with self._uow() as uow:
            updated, events = rules.heartbeat(self._load(uow, employee_id), now)
            uow.employees.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(updated)

    def seat_of(self, employee_id: str) -> str:
        """内部查询：员工当前工位；无工位或员工不存在返回空串，供公开事件定位。"""
        with self._uow() as uow:
            employee = uow.employees.get(employee_id)
        return (employee.seat_id or "") if employee is not None else ""

    def deregister(self, actor: Actor, employee_id: str, reason: str) -> EmployeeView:
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_REMOVE,
                Resource(kind="employee", team_id=target.team_id, owner_id=target.employee_id),
            )
            updated, events = rules.deregister(
                target, reason=reason, actor_id=actor.employee_id, now=now
            )
            uow.employees.save(updated)
            uow.sessions.revoke_all(employee_id, now)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(updated)

    def set_seat(self, actor: Actor, employee_id: str, seat_id: str | None) -> EmployeeView:
        """分配/释放工位：同一工位只允许一个未注销员工。"""
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.ORG_MANAGE,
                Resource(kind="employee", team_id=target.team_id),
            )
            if seat_id is not None:
                granted = inheritance.seat_capabilities(uow, seat_id)
                if not can_grant_capabilities(actor.capabilities, granted):
                    raise PermissionDeniedError("不能授予超出自身范围的能力")
                self._ensure_seat_available(uow, seat_id, employee_id)
            updated, events = rules.assign_seat(target, seat_id, now)
            updated, inherited = inheritance.inherit_from_seat(
                uow, updated, seat_id, now
            )
            events = (*events, *inherited)
            uow.employees.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(updated)

    def set_agent(self, actor: Actor, employee_id: str, agent_id: str | None) -> EmployeeView:
        """绑定/解绑 Agent 台账；仅具备全行管理权限的角色可操作。"""
        if agent_id is not None and not self._agents.summaries((agent_id,)):
            raise NotFoundError("Agent 不存在")
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.ORG_MANAGE,
                Resource(kind="employee", team_id=target.team_id),
            )
            updated, events = rules.set_agent(target, agent_id, now)
            uow.employees.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(updated)

    def update_endpoint(
        self, actor: Actor, employee_id: str, *,
        endpoint: str | None = None, approved: bool | None = None,
    ) -> EmployeeView:
        """端点补录与审核：写地址默认视为已审核；仅传 approved 保留旧语义。"""
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="employee")
            )
            if endpoint is not None:
                target, events = rules.set_endpoint(
                    target, endpoint, True if approved is None else approved, now
                )
            elif approved is not None:
                target, events = rules.set_endpoint_approved(target, approved, now)
            else:
                raise InvalidStateError("请提供端点地址或审核状态")
            uow.employees.save(target)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(target)

    def set_manager(self, actor: Actor, employee_id: str, enabled: bool) -> EmployeeView:
        """指定管理者：仅超管可操作；停用只移除 CONSOLE_ADMIN。"""
        now = self._clock.now()
        with self._uow() as uow:
            target = self._load(uow, employee_id)
            ensure_allowed(
                actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="employee")
            )
            updated, events = rules.set_manager(target, enabled, now)
            uow.employees.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return self._view(updated)

    def mark_stale_offline(self, cutoff: datetime) -> int:
        """心跳超时扫描：active 且最后心跳早于 cutoff 的员工置为 offline。"""
        now = self._clock.now()
        offline = 0
        with self._uow() as uow:
            for employee in uow.employees.list_stale_active(cutoff):
                updated, events = rules.mark_offline(employee, now)
                uow.employees.save(updated)
                enqueue_events(uow.outbox, events, self._ids, now)
                offline += 1
            if offline:
                uow.commit()
        return offline

    def list_staff(self, actor: Actor, status: str = "pending") -> tuple[EmployeeView, ...]:
        """员工列表：pending 仅待审，active 含离线，all 不做状态过滤。"""
        ensure_allowed(
            actor.to_subject(), Capability.EMPLOYEE_INVITE, Resource(kind="employee")
        )
        with self._uow() as uow:
            employees = uow.employees.list_all()
        employees = scoping.filter_by_scope(actor, employees)
        if status == "pending":
            employees = [
                employee
                for employee in employees
                if employee.status is EmployeeStatus.PENDING
            ]
        elif status == "active":
            employees = [
                employee
                for employee in employees
                if employee.status in ON_DUTY_STATUSES
            ]
        summaries = self._agent_summaries(employees)
        return tuple(
            employee_view(employee, summaries.get(employee.agent_id or ""))
            for employee in employees
        )

    def me(self, actor: Actor) -> EmployeeView:
        with self._uow() as uow:
            employee = self._load(uow, actor.employee_id)
        return self._view(employee)

    def get(self, actor: Actor, employee_id: str) -> EmployeeView:
        """员工详情：本人或具备邀请/管理能力者可读。"""
        with self._uow() as uow:
            employee = self._load(uow, employee_id)
        if actor.employee_id != employee_id:
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="employee", team_id=employee.team_id),
            )
        return self._view(employee)

    def occupants(self) -> tuple[OccupantView, ...]:
        """布局投影用：只返回座位与在线状态，不暴露能力等敏感字段。"""
        with self._uow() as uow:
            employees = uow.employees.list_all()
        return tuple(
            OccupantView(
                employee_id=employee.employee_id,
                display_name=employee.display_name,
                team_id=employee.team_id,
                position_id=employee.position_id,
                seat_id=employee.seat_id,
                agent_id=employee.agent_id,
                status=employee.status.value,
                last_heartbeat=employee.last_heartbeat,
            )
            for employee in employees
            if employee.status is not EmployeeStatus.DEREGISTERED
        )

    def _view(
        self, employee: Employee, summary: AgentSummary | None = None
    ) -> EmployeeView:
        if summary is None and employee.agent_id:
            summary = self._agents.summaries((employee.agent_id,)).get(employee.agent_id)
        return employee_view(employee, summary)

    def _agent_summaries(
        self, employees: list[Employee]
    ) -> dict[str, AgentSummary]:
        return self._agents.summaries(
            tuple(employee.agent_id for employee in employees if employee.agent_id)
        )

    def _register(
        self,
        uow: IdentityUnitOfWork,
        cmd: ApplyCommand,
        employee_id: str,
        now: datetime,
    ) -> tuple[Employee, tuple[DomainEvent, ...]]:
        if cmd.invite_code:
            invite = self._consume_invite(uow, cmd, employee_id, now)
            registration = Registration(
                employee_id=employee_id,
                display_name=cmd.display_name,
                account_type=invite.account_type,
                team_id=invite.team_id,
                position_id=invite.position_id,
                capabilities=inheritance.inherited_capabilities(
                    uow, invite.position_id, invite.capabilities
                ),
                data_scope=invite.data_scope,
                endpoint=cmd.endpoint,
                seat_id=cmd.seat_id,
                agent_id=cmd.agent_id,
                approved=True,
            )
            employee, events = rules.submit(registration, now)
            employee, activated = rules.activate(employee, now)
            return employee, (*events, *activated)
        registration = Registration(
            employee_id=employee_id,
            display_name=cmd.display_name,
            account_type=cmd.account_type,
            endpoint=cmd.endpoint,
            seat_id=cmd.seat_id,
            agent_id=cmd.agent_id,
            capabilities=inheritance.seat_capabilities(uow, cmd.seat_id),
        )
        employee, events = rules.submit(registration, now)
        return employee, events

    def _consume_invite(
        self,
        uow: IdentityUnitOfWork,
        cmd: ApplyCommand,
        employee_id: str,
        now: datetime,
    ) -> Invite:
        invite = uow.invites.get(cmd.invite_code or "")
        self._check_invite(invite, cmd, now)
        assert invite is not None
        if not uow.invites.consume(invite.invite_code, employee_id, now):
            raise InviteInvalidError("邀请码已被使用")
        return invite

    def _check_invite(self, invite: Invite | None, cmd: ApplyCommand, now: datetime) -> None:
        if invite is None:
            raise InviteInvalidError("邀请码不存在")
        if invite.consumed:
            raise InviteInvalidError("邀请码已被使用")
        if invite.expires_at is not None and invite.expires_at <= now:
            raise InviteInvalidError("邀请码已过期")
        if invite.account_type is not cmd.account_type:
            raise InviteInvalidError("邀请码与账号类型不匹配")

    def _ensure_seat_available(
        self, uow: IdentityUnitOfWork, seat_id: str, employee_id: str
    ) -> None:
        if seat_id not in self._seed.load().seat_index():
            raise NotFoundError("工位不存在")
        for other in uow.employees.list_all():
            if (
                other.employee_id != employee_id
                and other.seat_id == seat_id
                and other.status is not EmployeeStatus.DEREGISTERED
            ):
                raise InvalidStateError(f"工位已被 {other.display_name} 占用")

    def _load(self, uow: IdentityUnitOfWork, employee_id: str) -> Employee:
        employee = uow.employees.get(employee_id)
        if employee is None:
            raise NotFoundError("员工不存在")
        return employee
