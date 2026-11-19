"""Agent 协议模型的映射（wire ↔ application DTO）。"""

from __future__ import annotations

from mailbus.api.schemas.agents import AgentIn, AgentOut, AgentUpdateIn
from mailbus.application.agents.dto import (
    AgentCommand,
    AgentUpdateCommand,
    AgentView,
    make_agent_command,
    make_agent_update_command,
)


def to_agent_out(view: AgentView) -> AgentOut:
    return AgentOut(
        agent_id=view.agent_id,
        name=view.name,
        framework=view.framework,
        model=view.model,
        endpoint=view.endpoint,
        enabled=view.enabled,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def agent_command(payload: AgentIn) -> AgentCommand:
    return make_agent_command(
        name=payload.name,
        framework=payload.framework,
        model=payload.model,
        endpoint=payload.endpoint,
        enabled=payload.enabled,
    )


def agent_update_command(payload: AgentUpdateIn) -> AgentUpdateCommand:
    return make_agent_update_command(payload.model_dump(exclude_unset=True))
