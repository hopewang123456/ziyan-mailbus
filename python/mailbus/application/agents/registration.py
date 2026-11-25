"""Agent 邀请码与自助注册用例。"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

from mailbus.application.agents.dto import (
    AgentInviteCommand,
    AgentInviteView,
    AgentRegisterCommand,
    AgentRegistration,
)
from mailbus.application.identity.dto import Actor
from mailbus.core.agents.models import Agent, AgentInvite
from mailbus.core.agents.ports import AgentsUnitOfWork, TokenCipherPort
from mailbus.core.identity.models import Employee
from mailbus.core.identity.policy import Resource, ensure_allowed, ensure_grantable
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    ResourceGoneError,
    UnprocessableError,
)
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability, DataScope, FileScope

_HASH_LIMIT = 500
_DEFAULT_PERMISSIONS = ("message_read", "message_send", "result_submit")


class AgentRegistrationService:
    def __init__(
        self,
        uow_factory: Callable[[], AgentsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        cipher: TokenCipherPort,
        guard: Callable[[str], str],
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._cipher = cipher
        self._guard = guard

    # ---- 邀请码 ----

    def create_invite(self, actor: Actor, cmd: AgentInviteCommand) -> AgentInviteView:
        ensure_allowed(
            actor.to_subject(), Capability.CONSOLE_ADMIN, Resource(kind="agent_invite")
        )
        requested = frozenset(Capability(item) for item in cmd.permissions)
        data_scope = DataScope(cmd.data_scope)
        ensure_grantable(actor.capabilities, actor.data_scope, requested, data_scope)
        code = self._ids.new("mbreg")
        now = self._clock.now()
        expires = now + timedelta(hours=cmd.expires_in_hours) if cmd.expires_in_hours else None
        invite = AgentInvite(
            invite_id=self._ids.new("ainv"),
            code_hash=_hash_code(code),
            employee_name=cmd.employee_name,
            position_id=cmd.position_id,
            capabilities=frozenset(cmd.capabilities),
            permissions=frozenset(item.value for item in requested) or frozenset(
                _DEFAULT_PERMISSIONS
            ),
            data_scope=data_scope.value,
            agent_type=cmd.agent_type,
            channel_type=cmd.channel_type,
            expires_at=expires,
            created_by=actor.employee_id,
            created_at=now,
        )
        with self._uow() as uow:
            uow.agents.add_invite(invite)
            uow.commit()
        return AgentInviteView.of(invite, code)

    def list_invites(self, actor: Actor, limit: int, offset: int):
        ensure_allowed(
            actor.to_subject(), Capability.CONSOLE_ADMIN, Resource(kind="agent_invite")
        )
        with self._uow() as uow:
            rows, total = uow.agents.list_invites(limit, offset)
        return tuple(AgentInviteView.of(item) for item in rows), total

    def revoke_invite(self, actor: Actor, invite_id: str) -> AgentInviteView:
        ensure_allowed(
            actor.to_subject(), Capability.CONSOLE_ADMIN, Resource(kind="agent_invite")
        )
        now = self._clock.now()
        with self._uow() as uow:
            invite = uow.agents.get_invite(invite_id)
            if invite is None:
                raise NotFoundError("邀请码不存在")
            if invite.revoked:
                raise InvalidStateError("邀请码已作废")
            updated = replace(invite, revoked_at=now, revoked_by=actor.employee_id)
            uow.agents.save_invite(updated)
            uow.commit()
        return AgentInviteView.of(updated)

    # ---- 自助注册 ----

    def register(self, cmd: AgentRegisterCommand) -> AgentRegistration:
        now = self._clock.now()
        with self._uow() as uow:
            invite = uow.agents.get_invite_by_hash(_hash_code(cmd.invite_code))
            _ensure_invite(invite, now)
            assert invite is not None
            if not invite.position_id:
                raise UnprocessableError("Agent 员工缺少岗位，无法注册")
            endpoint = self._guard(cmd.endpoint) if cmd.endpoint else None
            token = self._ids.new("mbk")
            agent = _new_agent(self._ids, cmd, invite, endpoint, token, self._cipher, now)
            employee = _new_employee(self._ids, cmd, invite, endpoint, agent.agent_id, now)
            uow.agents.save(agent)
            uow.employees.save(employee)
            uow.agents.save_invite(
                replace(invite, used_by_agent_id=agent.agent_id, used_at=now)
            )
            uow.commit()
        return AgentRegistration(
            agent_id=agent.agent_id,
            employee_id=employee.employee_id,
            token=token,
            endpoint=endpoint,
            endpoint_review_status=agent.endpoint_review_status,
        )


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _ensure_invite(invite: AgentInvite | None, now) -> None:
    """校验顺序：不存在 404 → 已使用 409 → 已撤销/已过期 410。"""
    if invite is None:
        raise NotFoundError("邀请码无效")
    if invite.consumed:
        raise InvalidStateError("邀请码已被使用")
    if invite.revoked:
        raise ResourceGoneError("邀请码已作废")
    if invite.expires_at is not None and invite.expires_at <= now:
        raise ResourceGoneError("邀请码已过期")


def _new_agent(ids, cmd, invite, endpoint, token, cipher, now) -> Agent:
    return Agent(
        agent_id=ids.new("agent"),
        name=cmd.name.strip(),
        framework=cmd.framework.strip(),
        model=cmd.model,
        endpoint=None,
        enabled=True,
        created_at=now,
        updated_at=now,
        agent_type=invite.agent_type or cmd.agent_type,
        channel_type=invite.channel_type or cmd.channel_type,
        endpoint_token=cipher.encrypt(token),
        endpoint_token_lookup_hash=cipher.lookup_digest(token),
        last_seen_at=now,
        pending_endpoint=endpoint,
        endpoint_review_status="pending" if endpoint else "approved",
        endpoint_approved_at=None if endpoint else now,
    )


def _new_employee(ids, cmd, invite, endpoint, agent_id: str, now) -> Employee:
    permissions = frozenset(Capability(item) for item in invite.permissions)
    return Employee(
        employee_id=ids.new("emp"),
        display_name=(invite.employee_name or cmd.name).strip(),
        account_type=AccountType.AGENT,
        status=EmployeeStatus.ACTIVE,
        position_id=invite.position_id,
        skills=invite.capabilities,
        capabilities=permissions,
        data_scope=DataScope(invite.data_scope),
        file_scope=FileScope(),
        endpoint=endpoint,
        endpoint_approved=False,
        approved_at=now,
        last_heartbeat=now,
        agent_id=agent_id,
    )
