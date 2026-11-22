"""大屏、结对与协同消息/任务路由。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from mailbus.api.deps import PUBLIC, SELF, declares, get_actor
from mailbus.api.mappers import collab as mapper
from mailbus.api.mappers import message as message_mapper
from mailbus.api.mappers import tasks as task_mapper
from mailbus.api.schemas.collab import (
    CollabMessageIn,
    OkOut,
    PairIn,
    PairOut,
    PublicScreenIn,
    ScreenFocusIn,
    ScreenHeartbeatIn,
    ScreenIn,
    ScreenLeaveIn,
    ScreenOut,
)
from mailbus.api.schemas.message import MessageOut, PublicMessageOut
from mailbus.api.schemas.tasks import PublicTaskOut
from mailbus.api.sse import collab_event_stream
from mailbus.application.collab.screens import RegisterScreenCommand
from mailbus.core.shared.errors import CapacityError, NotFoundError, RateLimitedError
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/collab", tags=["collab"])
public_router = APIRouter(prefix="/api/public/collab", tags=["collab"])


def _service(request: Request):
    return request.app.state.container.screens


def _pairs(request: Request):
    return request.app.state.container.pairs


def _messages(request: Request):
    return request.app.state.container.collab_messages


def _bus(request: Request):
    return request.app.state.container.collab_events


def _ensure_stream_capacity(request: Request) -> None:
    """SSE 长连接上限：与管理端事件流共享同一闸门，超限返回 503。"""
    if request.app.state.container.stream_gate.full:
        raise CapacityError("大屏连接数已达上限，请稍后重试")


def _rate_limit(request: Request, endpoint: str) -> None:
    """公开端点 IP 限速：按 endpoint + client IP 分桶，超限返回 429。"""
    limiter = request.app.state.container.public_register_limiter
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(f"{endpoint}:{client}"):
        raise RateLimitedError("请求过于频繁，请稍后重试")


@router.get("/screens", response_model=list[ScreenOut], summary="大屏列表")
def list_screens(request: Request) -> list[ScreenOut]:
    get_actor(request)
    return [mapper.to_screen(view) for view in _service(request).list_screens()]


@router.post("/screens", response_model=ScreenOut, status_code=201, summary="登记大屏")
@declares(Capability.CONSOLE_ADMIN)
def register_screen(payload: ScreenIn, request: Request) -> ScreenOut:
    actor = get_actor(request)
    view = _service(request).register(
        actor,
        RegisterScreenCommand(
            screen_id=payload.screen_id,
            name=payload.name,
            floor_id=payload.floor_id,
            seat_id=payload.seat_id,
        ),
    )
    return mapper.to_screen(view)


@router.post(
    "/screens/{screen_id}/heartbeat", response_model=OkOut, summary="大屏心跳"
)
@declares(SELF)
def heartbeat(
    screen_id: str,
    request: Request,
    payload: ScreenHeartbeatIn | None = None,
) -> OkOut:
    get_actor(request)
    _service(request).heartbeat(
        screen_id,
        None if payload is None else payload.floor_id,
        None if payload is None else payload.seat_id,
        None if payload is None else payload.secret,
    )
    return OkOut()


@router.post(
    "/screens/{screen_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="大屏离线（管理端，免密钥）",
)
@declares(Capability.CONSOLE_ADMIN)
def leave(screen_id: str, request: Request) -> Response:
    _service(request).force_leave(get_actor(request), screen_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/screens/{screen_id}/focus",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="遥控聚焦",
)
@declares(Capability.CONSOLE_ADMIN)
def focus(screen_id: str, payload: ScreenFocusIn, request: Request) -> Response:
    _service(request).focus(
        get_actor(request), screen_id, payload.floor_id, payload.seat_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stream", summary="管理端大屏 SSE")
def stream(request: Request) -> StreamingResponse:
    get_actor(request)
    bus = _bus(request)
    _ensure_stream_capacity(request)
    return StreamingResponse(
        collab_event_stream(bus),
        media_type="text/event-stream",
    )


@router.get("/pairs", response_model=list[PairOut], summary="结对列表")
def list_pairs(
    request: Request,
    state: Literal["active", "ended"] | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PairOut]:
    actor = get_actor(request)
    views = _pairs(request).list_pairs(actor, state=state, limit=limit)
    return [mapper.to_pair(view) for view in views]


@router.post("/pairs", response_model=PairOut, status_code=201, summary="创建结对")
@declares(SELF)
def create_pair(payload: PairIn, request: Request) -> PairOut:
    return mapper.to_pair(_pairs(request).create(get_actor(request), payload.partner_id))


@router.post(
    "/pairs/{pair_id}/end",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="结束结对",
)
@declares(SELF)
def end_pair(pair_id: str, request: Request) -> Response:
    _pairs(request).end(get_actor(request), pair_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/messages", response_model=list[MessageOut], summary="协同消息列表")
def list_collab_messages(
    request: Request,
    pair_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MessageOut]:
    views = _messages(request).list_messages(
        get_actor(request), pair_id=pair_id, limit=limit
    )
    return [message_mapper.to_message_out(view) for view in views]


@router.post(
    "/messages", response_model=MessageOut, status_code=201, summary="发送协同消息"
)
@declares(Capability.MESSAGE_SEND)
def send_collab_message(payload: CollabMessageIn, request: Request) -> MessageOut:
    view = _messages(request).send(
        get_actor(request),
        pair_id=payload.pair_id,
        body=payload.body,
        recipient_id=payload.recipient_id,
        kind=payload.kind,
        channel=payload.channel,
    )
    return message_mapper.to_message_out(view)


@public_router.post(
    "/screens", response_model=ScreenOut, status_code=201, summary="公开登记大屏"
)
@declares(PUBLIC)
def public_register_screen(payload: PublicScreenIn, request: Request) -> ScreenOut:
    limiter = request.app.state.container.public_register_limiter
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        raise RateLimitedError("大屏登记过于频繁，请稍后重试")
    view = _service(request).register(
        None,
        RegisterScreenCommand(
            screen_id=payload.screen_id,
            name=payload.name,
            floor_id=payload.floor_id,
            seat_id=payload.seat_id,
        ),
    )
    return mapper.to_screen(view)


@public_router.post(
    "/screens/{screen_id}/heartbeat", response_model=OkOut, summary="公开大屏心跳"
)
@declares(PUBLIC)
def public_heartbeat(
    screen_id: str,
    request: Request,
    payload: ScreenHeartbeatIn | None = None,
) -> OkOut:
    _rate_limit(request, "screen.heartbeat")
    _service(request).heartbeat(
        screen_id,
        None if payload is None else payload.floor_id,
        None if payload is None else payload.seat_id,
        None if payload is None else payload.secret,
    )
    return OkOut()


@public_router.post(
    "/screens/{screen_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="大屏离线",
)
@declares(PUBLIC)
def public_leave(
    screen_id: str,
    request: Request,
    payload: ScreenLeaveIn | None = None,
) -> Response:
    _rate_limit(request, "screen.leave")
    _service(request).leave(screen_id, None if payload is None else payload.secret)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/stream", summary="公开大屏 SSE")
def public_stream(request: Request, screen_id: str | None = None) -> StreamingResponse:
    bus = _bus(request)
    _ensure_stream_capacity(request)
    return StreamingResponse(
        collab_event_stream(bus, screen_id=screen_id, public=True),
        media_type="text/event-stream",
    )


@public_router.get(
    "/messages", response_model=list[PublicMessageOut], summary="公开协同消息（脱敏）"
)
def public_collab_messages(
    request: Request,
    pair_id: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[PublicMessageOut]:
    views = _messages(request).list_public(pair_id, limit)
    return [message_mapper.to_public_message_out(view) for view in views]


@public_router.get(
    "/seats/{seat_id}/tasks",
    response_model=list[PublicTaskOut],
    summary="公开工位任务（按工位解析员工，不暴露员工标识）",
)
def public_seat_tasks(request: Request, seat_id: str) -> list[PublicTaskOut]:
    site = request.app.state.container.layout.get()
    for floor in site.floors:
        for room in floor.rooms:
            for seat in room.seats:
                if seat.seat_id != seat_id:
                    continue
                owner_id = seat.agent.agent_id if seat.agent else None
                if owner_id is None:
                    return []
                views = request.app.state.container.tasks.list_tasks(None, owner_id)
                return [task_mapper.to_public_task_out(view) for view in views]
    raise NotFoundError("工位不存在")


@public_router.get(
    "/tasks/{task_id}",
    response_model=PublicTaskOut,
    summary="公开任务详情（脱敏）；可选 owner_id 绑定，未知返回 404",
)
def public_collab_task(
    request: Request,
    task_id: str,
    owner_id: str | None = Query(default=None),
) -> PublicTaskOut:
    view = request.app.state.container.tasks.get(task_id, owner_id=owner_id)
    return task_mapper.to_public_task_out(view)
