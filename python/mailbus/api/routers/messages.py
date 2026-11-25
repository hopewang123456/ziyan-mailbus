"""消息路由：发送、详情与收件箱投影。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request, Response

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import message as mapper
from mailbus.api.schemas.contract.message import (
    MessageIn,
    MessageListOut,
    MessageOut,
    MessageTraceOut,
)
from mailbus.api.schemas.message import DeliveryAttemptOut
from mailbus.api.schemas.message import MessageOut as LegacyMessageOut
from mailbus.application.messaging.dto import make_send_command
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api", tags=["message"])


def _service(request: Request):
    return request.app.state.container.messages


@router.get("/inbox", response_model=list[LegacyMessageOut], summary="收件箱投影")
def list_inbox(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[LegacyMessageOut]:
    actor = get_actor(request)
    views = _service(request).inbox(actor, limit=limit, offset=offset)
    return [mapper.to_message_out(view) for view in views]


@router.get("/messages", response_model=MessageListOut, summary="消息检索")
def list_messages(
    request: Request,
    employee_id: str | None = None,
    channel: Literal["file_bus", "a2a", "mcp"] | None = None,
    kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> MessageListOut:
    actor = get_actor(request)
    service = _service(request)
    views = service.list_messages(
        actor,
        employee_id=employee_id,
        channel=channel,
        kind=kind,
        limit=limit,
        offset=offset,
    )
    total = service.count_messages(
        actor, employee_id=employee_id, channel=channel, kind=kind
    )
    return mapper.to_message_list_out(views, total, limit, offset)


@router.post(
    "/messages", response_model=MessageOut, status_code=201, summary="发送消息"
)
@declares(Capability.MESSAGE_SEND)
def send_message(payload: MessageIn, request: Request) -> MessageOut:
    view = _service(request).send(
        get_actor(request),
        make_send_command(payload.body, payload.recipient_id, payload.kind, payload.channel),
    )
    return mapper.to_contract_message_out(view)


@router.get("/messages/{message_id}", response_model=MessageOut, summary="消息详情")
def get_message(message_id: str, request: Request) -> MessageOut:
    return mapper.to_contract_message_out(
        _service(request).get(get_actor(request), message_id)
    )


@router.get(
    "/messages/{message_id}/trace",
    response_model=MessageTraceOut,
    summary="消息投递追迹",
)
def trace_message(message_id: str, request: Request) -> MessageTraceOut:
    actor = get_actor(request)
    service = _service(request)
    view = service.get(actor, message_id)
    attempts = service.attempts(actor, message_id)
    return mapper.to_trace_out(view, attempts)


@router.get(
    "/messages/{message_id}/attempts",
    response_model=list[DeliveryAttemptOut],
    summary="投递尝试（旧别名）",
    deprecated=True,
    include_in_schema=False,
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
