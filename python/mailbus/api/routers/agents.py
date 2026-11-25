"""Agent 台账路由：冻结契约实现 + 旧登记/更新别名（deprecated）。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import PUBLIC, declares, get_actor
from mailbus.api.mappers import agents as mapper
from mailbus.api.schemas.agents import AgentIn
from mailbus.api.schemas.agents import AgentOut as LegacyAgentOut
from mailbus.api.schemas.agents import AgentUpdateIn
from mailbus.api.schemas.contract.agent import (
    AgentHealthOut,
    AgentListOut,
    AgentOut,
    AgentRegisterIn,
    AgentRegisterOut,
    AgentTokenOut,
    EndpointDecisionIn,
)
from mailbus.application.agents.dto import (
    AgentAdminView,
    AgentRegisterCommand,
    AgentTokenResult,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/agents", tags=["agent"])


def _service(request: Request):
    return request.app.state.container.agents


@router.get("", response_model=AgentListOut, summary="Agent 外壳列表")
def list_agents(
    request: Request,
    enabled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AgentListOut:
    rows, total = _service(request).list_page(get_actor(request), limit, offset)
    items = [_agent_out(item) for item in rows if enabled is None or item.enabled == enabled]
    return AgentListOut(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/register", response_model=AgentRegisterOut, status_code=201, summary="Agent 自助注册"
)
@declares(PUBLIC)
def register_agent(payload: AgentRegisterIn, request: Request) -> AgentRegisterOut:
    result = request.app.state.container.agent_registration.register(
        AgentRegisterCommand(
            invite_code=payload.invite_code,
            name=payload.name,
            framework=payload.framework,
            model=payload.model,
            endpoint=payload.endpoint,
            agent_type=payload.agent_type,
            channel_type=payload.channel_type,
        )
    )
    return AgentRegisterOut(
        agent_id=result.agent_id,
        employee_id=result.employee_id,
        token=result.token,
        endpoint=result.endpoint,
        endpoint_review_status=result.endpoint_review_status,
    )


@router.get("/{agent_id}", response_model=AgentOut, summary="Agent 详情")
def get_agent(agent_id: str, request: Request) -> AgentOut:
    return _agent_out(_service(request).get_detail(get_actor(request), agent_id))


@router.delete("/{agent_id}", status_code=204, summary="注销 Agent")
@declares(Capability.AGENT_DEREGISTER)
def delete_agent(agent_id: str, request: Request) -> None:
    _service(request).delete(get_actor(request), agent_id)


@router.post(
    "/{agent_id}/rotate-token", response_model=AgentTokenOut, summary="轮转 Agent token"
)
@declares(Capability.CONSOLE_ADMIN)
def rotate_token(agent_id: str, request: Request) -> AgentTokenOut:
    return _token_out(_service(request).rotate_token(get_actor(request), agent_id))


@router.post(
    "/{agent_id}/revoke-token", response_model=AgentOut, summary="吊销 Agent token"
)
@declares(Capability.CONSOLE_ADMIN)
def revoke_token(agent_id: str, request: Request) -> AgentOut:
    return _agent_out(_service(request).revoke_token(get_actor(request), agent_id))


@router.post("/{agent_id}/unbind", response_model=AgentOut, summary="解除员工绑定")
@declares(Capability.AGENT_DEREGISTER)
def unbind_agent(agent_id: str, request: Request) -> AgentOut:
    return _agent_out(_service(request).unbind(get_actor(request), agent_id))


@router.post(
    "/{agent_id}/health", response_model=AgentHealthOut, summary="Agent 健康检查"
)
@declares(Capability.CONSOLE_ADMIN)
def agent_health(agent_id: str, request: Request) -> AgentHealthOut:
    view = _service(request).health(get_actor(request), agent_id)
    return AgentHealthOut(
        agent_id=view.agent_id,
        online=view.online,
        endpoint_ok=view.endpoint_review_status == "approved" and bool(view.endpoint),
        last_seen_at=view.last_seen_at,
    )


@router.post(
    "/{agent_id}/endpoint/approve", response_model=AgentOut, summary="批准 endpoint"
)
@declares(Capability.CONSOLE_ADMIN)
def approve_endpoint(
    agent_id: str, request: Request, payload: EndpointDecisionIn | None = None
) -> AgentOut:
    return _agent_out(_service(request).approve_endpoint(get_actor(request), agent_id))


@router.post(
    "/{agent_id}/endpoint/reject", response_model=AgentOut, summary="拒绝 endpoint"
)
@declares(Capability.CONSOLE_ADMIN)
def reject_endpoint(
    agent_id: str, request: Request, payload: EndpointDecisionIn | None = None
) -> AgentOut:
    return _agent_out(_service(request).reject_endpoint(get_actor(request), agent_id))


def _agent_out(view: AgentAdminView) -> AgentOut:
    return AgentOut(
        agent_id=view.agent_id,
        name=view.name,
        framework=view.framework,
        model=view.model,
        endpoint=view.endpoint,
        pending_endpoint=view.pending_endpoint,
        endpoint_review_status=view.endpoint_review_status,
        enabled=view.enabled,
        agent_type=view.agent_type,
        channel_type=view.channel_type,
        online=view.online,
        last_seen_at=view.last_seen_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _token_out(result: AgentTokenResult) -> AgentTokenOut:
    return AgentTokenOut(
        agent_id=result.agent_id,
        token=result.token,
        fingerprint=result.fingerprint,
        expires_at=result.expires_at,
    )


# ---- 旧别名：保留实现，但不进入契约 ----


@router.post(
    "",
    response_model=LegacyAgentOut,
    status_code=201,
    summary="登记 Agent（旧别名）",
    deprecated=True,
    include_in_schema=False,
)
@declares(Capability.SYSTEM_CONFIG)
def create_agent(payload: AgentIn, request: Request) -> LegacyAgentOut:
    view = _service(request).create(get_actor(request), mapper.agent_command(payload))
    return mapper.to_agent_out(view)


@router.patch(
    "/{agent_id}",
    response_model=LegacyAgentOut,
    summary="更新 Agent（旧别名）",
    deprecated=True,
    include_in_schema=False,
)
@declares(Capability.SYSTEM_CONFIG)
def update_agent(
    agent_id: str, payload: AgentUpdateIn, request: Request
) -> LegacyAgentOut:
    view = _service(request).update(
        get_actor(request), agent_id, mapper.agent_update_command(payload)
    )
    return mapper.to_agent_out(view)
