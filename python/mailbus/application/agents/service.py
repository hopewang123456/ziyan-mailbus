"""Agent 台账用例：登记、更新、查询。

台账只负责登记与展示；进程启停和运行时执行不在本服务范围。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from mailbus.application.agents.dto import (
    AgentAdminView,
    AgentCommand,
    AgentTokenResult,
    AgentUpdateCommand,
    AgentView,
    agent_view,
)
from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.core.agents import rules
from mailbus.core.agents.models import Agent
from mailbus.core.agents.ports import AgentsUnitOfWork, TokenCipherPort
from mailbus.core.identity import rules as identity_rules
from mailbus.core.identity.policy import Resource, ensure_allowed, ensure_any_allowed
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.shared.errors import InvalidStateError, NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class AgentService:
    def __init__(
        self,
        uow_factory: Callable[[], AgentsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        cipher: TokenCipherPort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._cipher = cipher

    def create(self, actor: Actor, cmd: AgentCommand) -> AgentView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            agent, events = rules.create_agent(
                self._ids.new("agent"),
                name=cmd.name,
                framework=cmd.framework,
                model=cmd.model,
                endpoint=cmd.endpoint,
                enabled=cmd.enabled,
                now=now,
            )
            uow.agents.save(agent)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return agent_view(agent)

    def update(self, actor: Actor, agent_id: str, cmd: AgentUpdateCommand) -> AgentView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
            updated, events = rules.update_agent(agent, cmd.changes, now)
            uow.agents.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return agent_view(updated)

    def list_all(self) -> tuple[AgentView, ...]:
        with self._uow() as uow:
            agents = uow.agents.list_all()
        return tuple(agent_view(agent) for agent in agents)

    def delete(self, actor: Actor, agent_id: str) -> None:
        """协同端注销：仍被未注销员工绑定时拒绝；通过后软删除并吊销 token。"""
        ensure_allowed(
            actor.to_subject(), Capability.AGENT_DEREGISTER, Resource(kind="agent")
        )
        now = self._clock.now()
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
            bound = any(
                employee.agent_id == agent_id
                and employee.status is not EmployeeStatus.DEREGISTERED
                for employee in uow.employees.list_all()
            )
            if bound:
                raise InvalidStateError("Agent 仍被员工绑定，请先解除绑定")
            uow.agents.soft_delete(agent_id, actor.employee_id, now)
            enqueue_events(uow.outbox, rules.delete_agent(agent, now), self._ids, now)
            uow.commit()

    def unbind(self, actor: Actor, agent_id: str) -> AgentAdminView:
        ensure_allowed(
            actor.to_subject(), Capability.AGENT_DEREGISTER, Resource(kind="agent")
        )
        now = self._clock.now()
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
            for employee in uow.employees.list_all():
                if (employee.agent_id != agent_id
                        or employee.status is EmployeeStatus.DEREGISTERED):
                    continue
                updated, events = identity_rules.set_agent(employee, None, now)
                uow.employees.save(updated)
                enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return AgentAdminView.of(agent, online=rules.is_online(agent, now))

    def list_page(self, actor: Actor, limit: int, offset: int):
        ensure_allowed(
            actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="agent")
        )
        now = self._clock.now()
        with self._uow() as uow:
            rows, total = uow.agents.list_page(limit, offset)
        views = tuple(
            AgentAdminView.of(item, online=rules.is_online(item, now)) for item in rows
        )
        return views, total

    def get_detail(self, actor: Actor, agent_id: str) -> AgentAdminView:
        ensure_allowed(
            actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="agent")
        )
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
        return AgentAdminView.of(agent, online=rules.is_online(agent, self._clock.now()))

    def approve_endpoint(self, actor: Actor, agent_id: str) -> AgentAdminView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
            updated = rules.approve_endpoint(agent, actor.employee_id, now)
            uow.agents.save(updated)
            self._sync_employee_endpoint(uow, updated, approved=True)
            uow.commit()
        return AgentAdminView.of(updated, online=rules.is_online(updated, now))

    def reject_endpoint(self, actor: Actor, agent_id: str) -> AgentAdminView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
            updated = rules.reject_endpoint(agent, actor.employee_id, now)
            uow.agents.save(updated)
            if not updated.endpoint:
                self._sync_employee_endpoint(uow, updated, approved=False)
            uow.commit()
        return AgentAdminView.of(updated, online=rules.is_online(updated, now))

    def rotate_token(self, actor: Actor, agent_id: str) -> AgentTokenResult:
        self._require(actor)
        now = self._clock.now()
        token = self._ids.new("mbk")
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
            updated, events = rules.rotate_token(
                agent,
                ciphertext=self._cipher.encrypt(token),
                lookup_hash=self._cipher.lookup_digest(token),
                now=now,
            )
            uow.agents.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return AgentTokenResult(
            agent_id=updated.agent_id,
            token=token,
            fingerprint=self._cipher.fingerprint(token),
            expires_at=updated.endpoint_token_prev_expires_at,
        )

    def revoke_token(self, actor: Actor, agent_id: str) -> AgentAdminView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            agent = self._load(uow, agent_id)
            updated, events = rules.revoke_token(agent, now)
            uow.agents.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return AgentAdminView.of(updated, online=False)

    def health(self, actor: Actor, agent_id: str) -> AgentAdminView:
        return self.get_detail(actor, agent_id)

    @staticmethod
    def _sync_employee_endpoint(uow, agent: Agent, *, approved: bool) -> None:
        for employee in uow.employees.list_all():
            if employee.agent_id == agent.agent_id:
                uow.employees.save(
                    replace(
                        employee,
                        endpoint=agent.endpoint,
                        endpoint_approved=approved and bool(agent.endpoint),
                    )
                )

    @staticmethod
    def _require(actor: Actor) -> None:
        ensure_any_allowed(
            actor.to_subject(),
            (Capability.SYSTEM_CONFIG, Capability.CONSOLE_ADMIN),
            Resource(kind="agent"),
        )

    @staticmethod
    def _load(uow: AgentsUnitOfWork, agent_id: str) -> Agent:
        agent = uow.agents.get(agent_id)
        if agent is None:
            raise NotFoundError("Agent 不存在")
        return agent
