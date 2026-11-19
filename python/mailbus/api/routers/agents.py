"""Agent 台账路由：登记、更新与查询。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import agents as mapper
from mailbus.api.schemas.agents import AgentIn, AgentOut, AgentUpdateIn
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/agents", tags=["agent"])


def _service(request: Request):
    return request.app.state.container.agents


@router.get("", response_model=list[AgentOut], summary="Agent 台账")
def list_agents(request: Request) -> list[AgentOut]:
    get_actor(request)
    return [mapper.to_agent_out(view) for view in _service(request).list_all()]


@router.post("", response_model=AgentOut, status_code=201, summary="登记 Agent")
@declares(Capability.SYSTEM_CONFIG)
def create_agent(payload: AgentIn, request: Request) -> AgentOut:
    view = _service(request).create(get_actor(request), mapper.agent_command(payload))
    return mapper.to_agent_out(view)


@router.patch("/{agent_id}", response_model=AgentOut, summary="更新 Agent")
@declares(Capability.SYSTEM_CONFIG)
def update_agent(agent_id: str, payload: AgentUpdateIn, request: Request) -> AgentOut:
    view = _service(request).update(
        get_actor(request), agent_id, mapper.agent_update_command(payload)
    )
    return mapper.to_agent_out(view)
