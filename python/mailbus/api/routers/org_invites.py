"""真人邀请路由：撤销、重发与公开接受。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mailbus.api.deps import PUBLIC, declares, get_actor
from mailbus.api.mappers import org_admin as mapper
from mailbus.api.schemas.contract.org import InviteAcceptIn, InviteAcceptOut, InviteOut
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api", tags=["org"])


def _svc(request: Request):
    return request.app.state.container.org_admin


@router.post(
    "/invites/{invite_id}/revoke", response_model=InviteOut, summary="撤销真人邀请"
)
@declares(Capability.EMPLOYEE_INVITE)
def revoke_invite(invite_id: str, request: Request) -> InviteOut:
    return mapper.to_invite_out(_svc(request).invites.revoke(get_actor(request), invite_id))


@router.post(
    "/invites/{invite_id}/resend", response_model=InviteOut, summary="重发真人邀请"
)
@declares(Capability.EMPLOYEE_INVITE)
def resend_invite(invite_id: str, request: Request) -> InviteOut:
    return mapper.to_invite_out(_svc(request).invites.resend(get_actor(request), invite_id))


@router.post(
    "/invites/accept",
    response_model=InviteAcceptOut,
    status_code=201,
    summary="接受真人邀请",
)
@declares(PUBLIC)
def accept_invite(payload: InviteAcceptIn, request: Request) -> InviteAcceptOut:
    view, token = _svc(request).invites.accept(
        payload.invite_code, payload.display_name
    )
    return InviteAcceptOut(employee=mapper.employee_out(view), token=token)
