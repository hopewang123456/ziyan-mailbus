"""Agent 台账的只读目录：批量摘要查询（员工视图 / 布局投影共用）。"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.core.agents.models import AgentSummary
from mailbus.core.agents.ports import AgentsUnitOfWork


class AgentDirectory:
    def __init__(self, uow_factory: Callable[[], AgentsUnitOfWork]) -> None:
        self._uow = uow_factory

    def summaries(self, agent_ids: tuple[str, ...]) -> dict[str, AgentSummary]:
        wanted = {agent_id for agent_id in agent_ids if agent_id}
        if not wanted:
            return {}
        with self._uow() as uow:
            agents = uow.agents.list_all()
        return {
            agent.agent_id: AgentSummary(
                agent_id=agent.agent_id,
                name=agent.name,
                framework=agent.framework,
            )
            for agent in agents
            if agent.agent_id in wanted
        }
