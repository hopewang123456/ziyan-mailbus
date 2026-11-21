"""消息路由：发送、详情与收件箱投影。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Request, Response

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import message as mapper
from mailbus.api.schemas.message import DeliveryAttemptOut, MessageIn, MessageOut
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api", tags=["message"])


def _service(request: Request):
    return request.app.state.container.messages


@router.get("/inbox", response_model=list[MessageOut], summary="收件箱投影")
def list_inbox(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[MessageOut]:
    actor = get_actor(request)
    views = _service(request).inbox(actor, limit=limit, offset=offset)
    return [mapper.to_message_out(view) for view in views]


@router.get("/messages", response_model=list[MessageOut], summary="消息检索")
def list_messages(
    request: Request,
    agent: str | None = None,
    status: Literal["pending", "delivered", "failed"] | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[MessageOut]:
    views = _service(request).list_messages(
        get_actor(request),
        agent=agent,
        status=status,
        since=since,
        limit=limit,
        offset=offset,
    )
    return [mapper.to_message_out(view) for view in views]


@router.post("/messages", response_model=MessageOut, status_code=201, summary="发送消息")
@declares(Capability.MESSAGE_SEND)
def send_message(payload: MessageIn, request: Request) -> MessageOut:
    view = _service(request).send(get_actor(request), mapper.message_command(payload))
    return mapper.to_message_out(view)


@router.get("/messages/{message_id}", response_model=MessageOut, summary="消息详情")
def get_message(message_id: str, request: Request) -> MessageOut:
    actor = get_actor(request)
    return mapper.to_message_out(_service(request).get(actor, message_id))


@router.get(
    "/messages/{message_id}/attempts",
    response_model=list[DeliveryAttemptOut],
    summary="投递尝试",
)
def list_attempts(message_id: str, request: Request) -> list[DeliveryAttemptOut]:
    actor = get_actor(request)
    views = _service(request).attempts(actor, message_id)
    return [mapper.to_attempt_out(view) for view in views]


@router.delete("/messages/{message_id}", status_code=204, summary="删除消息")
@declares(Capability.SYSTEM_CONFIG)
def delete_message(message_id: str, request: Request) -> Response:
    _service(request).delete(get_actor(request), message_id)
    return Response(status_code=204)
