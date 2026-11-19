"""Agent 用例的输入/输出模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.agents.models import Agent


@dataclass(frozen=True, slots=True)
class AgentCommand:
    name: str
    framework: str = ""
    model: str | None = None
    endpoint: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AgentUpdateCommand:
    """只携带客户端显式提交的字段（PATCH 语义）。"""

    changes: dict[str, object]


@dataclass(frozen=True, slots=True)
class AgentView:
    agent_id: str
    name: str
    framework: str
    model: str | None
    endpoint: str | None
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def of(cls, agent: Agent) -> "AgentView":
        return cls(
            agent_id=agent.agent_id,
            name=agent.name,
            framework=agent.framework,
            model=agent.model,
            endpoint=agent.endpoint,
            enabled=agent.enabled,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


def agent_view(agent: Agent) -> AgentView:
    return AgentView.of(agent)


def make_agent_command(
    name: str,
    framework: str = "",
    model: str | None = None,
    endpoint: str | None = None,
    enabled: bool = True,
) -> AgentCommand:
    return AgentCommand(
        name=name,
        framework=framework,
        model=model,
        endpoint=endpoint,
        enabled=enabled,
    )


def make_agent_update_command(changes: dict[str, object]) -> AgentUpdateCommand:
    return AgentUpdateCommand(changes=dict(changes))
