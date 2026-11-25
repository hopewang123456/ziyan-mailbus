"""真人邀请用例：签发、撤销、重发与接受。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor, EmployeeView
from mailbus.application.identity.sessions import issue_session
from mailbus.application.org.admin_ports import OrgAdminUnitOfWork
from mailbus.application.org.invite_views import AdminInviteView
from mailbus.core.identity import rules
from mailbus.core.identity.errors import InviteGoneError
from mailbus.core.identity.models import Invite, Registration
from mailbus.core.identity.policy import (
    Resource,
    can_grant_capabilities,
    ensure_allowed,
    ensure_grantable,
    scope_is_within,
)
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableError,
)
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability, DataScope

DEFAULT_TTL_HOURS = 24


class InviteAdminService:
    def __init__(
        self,
        uow_factory: Callable[[], OrgAdminUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def issue(
        self,
        actor: Actor,
        display_name: str,
        position_id: str | None,
        team_id: str | None,
        data_scope: DataScope,
        permissions: list[str],
        expires_in_hours: int,
    ) -> AdminInviteView:
        now = self._clock.now()
        granted = self._capabilities(permissions)
        ensure_grantable(actor.capabilities, actor.data_scope, granted, data_scope)
        with self._uow() as uow:
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="team", team_id=team_id),
            )
            self._ensure_targets(uow, team_id, position_id)
            invite = Invite(
                invite_code=self._ids.new("inv"),
                account_type=AccountType.HUMAN,
                team_id=team_id,
                position_id=position_id,
                data_scope=data_scope,
                permissions=granted,
                created_by=actor.employee_id,
                created_at=now,
                expires_at=now + timedelta(hours=expires_in_hours),
            )
            uow.invites.add(invite)
            uow.commit()
        return AdminInviteView.of(invite, plaintext=True)

    def revoke(self, actor: Actor, invite_id: str) -> AdminInviteView:
        now = self._clock.now()
        with self._uow() as uow:
            invite = self._load(uow, invite_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="team", team_id=invite.team_id),
            )
            if invite.consumed:
                raise InvalidStateError("邀请码已被使用，无法撤销")
            if not invite.revoked:
                uow.invites.revoke(invite_id, actor.employee_id, now)
                refreshed = uow.invites.get(invite_id)
                invite = refreshed or invite
                uow.commit()
        return AdminInviteView.of(invite)

    def resend(self, actor: Actor, invite_id: str) -> AdminInviteView:
        now = self._clock.now()
        with self._uow() as uow:
            old = self._load(uow, invite_id)
            ensure_allowed(
                actor.to_subject(),
                Capability.EMPLOYEE_INVITE,
                Resource(kind="team", team_id=old.team_id),
            )
            if old.consumed:
                raise InvalidStateError("邀请码已被使用，请重新创建邀请")
            ensure_grantable(
                actor.capabilities, actor.data_scope, old.permissions, old.data_scope
            )
            self._ensure_targets(uow, old.team_id, old.position_id)
            if not old.revoked:
                uow.invites.revoke(invite_id, actor.employee_id, now)
            invite = Invite(
                invite_code=self._ids.new("inv"),
                account_type=old.account_type,
                team_id=old.team_id,
                position_id=old.position_id,
                data_scope=old.data_scope,
                permissions=old.permissions,
                created_by=actor.employee_id,
                created_at=now,
                expires_at=now + timedelta(hours=DEFAULT_TTL_HOURS),
            )
            uow.invites.add(invite)
            uow.commit()
        return AdminInviteView.of(invite, plaintext=True)

    def accept(self, invite_code: str, display_name: str | None) -> tuple[EmployeeView, str]:
        now = self._clock.now()
        with self._uow() as uow:
            invite = uow.invites.get(invite_code)
            if invite is None:
                raise NotFoundError("邀请码不存在")
            if invite.revoked or invite.consumed:
                raise InviteGoneError("邀请链接已失效")
            if invite.expires_at is not None and invite.expires_at <= now:
                raise InviteGoneError("邀请链接已失效")
            self._ensure_inviter(uow, invite)
            position = (
                uow.positions.get(invite.position_id) if invite.position_id else None
            )
            if invite.position_id and position is None:
                raise InviteGoneError("邀请关联的岗位已不存在")
            registration = Registration(
                employee_id=self._ids.new("emp"),
                display_name=(display_name or "新员工").strip() or "新员工",
                account_type=invite.account_type,
                team_id=invite.team_id,
                position_id=invite.position_id,
                capabilities=invite.permissions,
                skills=position.capabilities if position else frozenset(),
                data_scope=invite.data_scope,
                approved=True,
            )
            employee, events = rules.submit(registration, now)
            employee, activated = rules.activate(employee, now)
            uow.employees.save(employee)
            if not uow.invites.consume(invite_code, employee.employee_id, now):
                raise InviteGoneError("邀请链接已失效")
            token = issue_session(uow, employee, self._ids, now)
            enqueue_events(uow.outbox, (*events, *activated), self._ids, now)
            uow.commit()
        return EmployeeView.of(employee), token

    def _ensure_inviter(self, uow: OrgAdminUnitOfWork, invite: Invite) -> None:
        inviter = (
            uow.employees.get(invite.created_by) if invite.created_by else None
        )
        if inviter is None or inviter.status in (
            EmployeeStatus.PENDING,
            EmployeeStatus.DEREGISTERED,
        ):
            raise PermissionDeniedError("邀请人已失效")
        if not can_grant_capabilities(inviter.capabilities, invite.permissions):
            raise PermissionDeniedError("邀请人已无权授予该权限")
        if not scope_is_within(inviter.data_scope, invite.data_scope):
            raise PermissionDeniedError("邀请人的数据范围已收窄")

    def _load(self, uow: OrgAdminUnitOfWork, invite_id: str) -> Invite:
        invite = uow.invites.get(invite_id)
        if invite is None:
            raise NotFoundError("邀请不存在")
        return invite

    def _ensure_targets(
        self,
        uow: OrgAdminUnitOfWork,
        team_id: str | None,
        position_id: str | None,
    ) -> None:
        if team_id is not None and uow.teams.get(team_id) is None:
            raise NotFoundError("团队不存在")
        if position_id is not None and uow.positions.get(position_id) is None:
            raise NotFoundError("岗位不存在")

    @staticmethod
    def _capabilities(values: list[str]) -> frozenset[Capability]:
        try:
            return frozenset(Capability(value) for value in dict.fromkeys(values))
        except ValueError as exc:
            raise UnprocessableError("存在未知权限值") from exc
