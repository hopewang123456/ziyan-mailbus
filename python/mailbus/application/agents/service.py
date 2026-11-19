"""Agent 台账用例：登记、更新、查询。

台账只负责登记与展示；进程启停和运行时执行不在本服务范围。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.agents.dto import (
    AgentCommand,
    AgentUpdateCommand,
    AgentView,
    agent_view,
)
from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.core.agents import rules
from mailbus.core.agents.models import Agent
from mailbus.core.agents.ports import AgentsUnitOfWork
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.errors import NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class AgentService:
    def __init__(
        self,
        uow_factory: Callable[[], AgentsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

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

    @staticmethod
    def _require(actor: Actor) -> None:
        ensure_allowed(
            actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="agent")
        )

    @staticmethod
    def _load(uow: AgentsUnitOfWork, agent_id: str) -> Agent:
        agent = uow.agents.get(agent_id)
        if agent is None:
            raise NotFoundError("Agent 不存在")
        return agent
