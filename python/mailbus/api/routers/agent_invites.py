"""Agent 邀请码：生成、列表与作废。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.schemas.contract.agent import (
    AgentInviteIn,
    AgentInviteListOut,
    AgentInviteOut,
)
from mailbus.application.agents.dto import AgentInviteCommand, AgentInviteView
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/agent-invites", tags=["agent"])


def _service(request: Request):
    return request.app.state.container.agent_registration


@router.get("", response_model=AgentInviteListOut, summary="Agent 邀请码列表")
def list_invites(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AgentInviteListOut:
    rows, total = _service(request).list_invites(get_actor(request), limit, offset)
    return AgentInviteListOut(
        items=[_invite_out(item) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AgentInviteOut, status_code=201, summary="生成邀请码")
@declares(Capability.CONSOLE_ADMIN)
def create_invite(payload: AgentInviteIn, request: Request) -> AgentInviteOut:
    view = _service(request).create_invite(
        get_actor(request),
        AgentInviteCommand(
            employee_name=payload.employee_name,
            position_id=payload.position_id,
            capabilities=tuple(payload.capabilities),
            permissions=tuple(payload.permissions),
            data_scope=payload.data_scope,
            agent_type=payload.agent_type,
            channel_type=payload.channel_type,
            expires_in_hours=payload.expires_in_hours,
        ),
    )
    return _invite_out(view)


@router.post(
    "/{invite_id}/revoke", response_model=AgentInviteOut, summary="作废邀请码"
)
@declares(Capability.CONSOLE_ADMIN)
def revoke_invite(invite_id: str, request: Request) -> AgentInviteOut:
    return _invite_out(_service(request).revoke_invite(get_actor(request), invite_id))


def _invite_out(view: AgentInviteView) -> AgentInviteOut:
    return AgentInviteOut(
        invite_id=view.invite_id,
        invite_code=view.invite_code,
        employee_name=view.employee_name,
        position_id=view.position_id,
        capabilities=list(view.capabilities),
        permissions=list(view.permissions),
        data_scope=view.data_scope,
        agent_type=view.agent_type,
        channel_type=view.channel_type,
        created_by=view.created_by,
        created_at=view.created_at,
        expires_at=view.expires_at,
        used_by_agent_id=view.used_by_agent_id,
        used_at=view.used_at,
        revoked_at=view.revoked_at,
    )
