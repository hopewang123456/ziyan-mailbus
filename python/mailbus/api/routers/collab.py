"""大屏、结对与协同消息/任务路由。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from mailbus.api.deps import PUBLIC, SELF, declares, get_actor
from mailbus.api.mappers import collab as mapper
from mailbus.api.mappers import message as message_mapper
from mailbus.api.mappers import tasks as task_mapper
from mailbus.api.schemas.collab import CollabMessageIn, OkOut, PairIn, PairOut
from mailbus.api.schemas.contract.screen import (
    PublicScreenConfigOut,
    ScreenConfigOut,
    ScreenDraftIn,
    ScreenFocusIn,
    ScreenHeartbeatIn,
    ScreenListOut,
    ScreenPublishIn,
    ScreenPublishOut,
    ScreenRegisterIn,
    ScreenRegisterOut,
)
from mailbus.api.schemas.message import MessageOut, PublicMessageOut
from mailbus.api.schemas.tasks import PublicTaskOut
from mailbus.api.sse import collab_event_stream
from mailbus.application.collab.screens import (
    RegisterScreenCommand,
    ScreenDraftCommand,
)
from mailbus.core.shared.errors import CapacityError, NotFoundError
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/collab", tags=["collab"])
public_router = APIRouter(prefix="/api/public/collab", tags=["collab"])


def _screens(request: Request):
    return request.app.state.container.screens


def _pairs(request: Request):
    return request.app.state.container.pairs


def _messages(request: Request):
    return request.app.state.container.collab_messages


def _bus(request: Request):
    return request.app.state.container.collab_events


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _ensure_stream_capacity(request: Request) -> None:
    """SSE 长连接上限：与管理端事件流共享同一闸门，超限返回 503。"""
    if request.app.state.container.stream_gate.full:
        raise CapacityError("大屏连接数已达上限，请稍后重试")


@router.get("/screens", response_model=ScreenListOut, summary="协同大屏列表")
def list_screens(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ScreenListOut:
    views, total = _screens(request).list_page(get_actor(request), limit, offset)
    return ScreenListOut(
        items=[mapper.to_screen_view(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/screens/{screen_id}", response_model=ScreenConfigOut, summary="接管/保存草稿"
)
@declares(Capability.CONSOLE_ADMIN)
def update_screen(
    screen_id: str, payload: ScreenDraftIn, request: Request
) -> ScreenConfigOut:
    config = payload.config.model_dump() if payload.config is not None else None
    view = _screens(request).save_draft(
        get_actor(request),
        screen_id,
        ScreenDraftCommand(config=config, play_state=payload.play_state),
    )
    return mapper.to_screen_config(view)


@router.post(
    "/screens/{screen_id}/publish",
    response_model=ScreenPublishOut,
    summary="发布大屏配置",
)
@declares(Capability.CONSOLE_ADMIN)
def publish_screen(
    screen_id: str, payload: ScreenPublishIn, request: Request
) -> ScreenPublishOut:
    version, published_at = _screens(request).publish(
        get_actor(request), screen_id, payload.expected_config_version
    )
    return ScreenPublishOut(config_version=version, published_at=published_at)


@router.post(
    "/screens/{screen_id}/focus",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="遥控聚焦",
)
@declares(Capability.CONSOLE_ADMIN)
def focus(screen_id: str, payload: ScreenFocusIn, request: Request) -> None:
    _screens(request).focus(
        get_actor(request), screen_id, payload.floor_id, payload.seat_id
    )


@router.delete(
    "/screens/{screen_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除大屏",
)
@declares(Capability.CONSOLE_ADMIN)
def delete_screen(screen_id: str, request: Request) -> None:
    _screens(request).delete(get_actor(request), screen_id)


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
    "/screens", response_model=ScreenRegisterOut, status_code=201, summary="自动登记大屏"
)
@declares(PUBLIC)
def public_register_screen(
    payload: ScreenRegisterIn, request: Request
) -> ScreenRegisterOut:
    view, secret = _screens(request).register(
        _client_ip(request),
        RegisterScreenCommand(
            screen_id=payload.screen_id,
            secret=payload.secret,
            name=payload.name,
            floor_id=payload.floor_id,
            seat_id=payload.seat_id,
        ),
    )
    return ScreenRegisterOut(
        screen_id=view.screen_id,
        screen_secret=secret,
        config_version=view.config_version,
    )


@public_router.post(
    "/screens/{screen_id}/heartbeat", response_model=OkOut, summary="公开大屏心跳"
)
@declares(PUBLIC)
def public_heartbeat(
    screen_id: str,
    request: Request,
    payload: ScreenHeartbeatIn | None = None,
    x_screen_secret: str | None = Header(default=None, alias="X-Screen-Secret"),
) -> OkOut:
    _screens(request).heartbeat(_client_ip(request), screen_id, x_screen_secret)
    return OkOut()


@public_router.post(
    "/screens/{screen_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="公开大屏离线",
)
@declares(PUBLIC)
def public_leave(
    screen_id: str,
    request: Request,
    x_screen_secret: str | None = Header(default=None, alias="X-Screen-Secret"),
) -> None:
    _screens(request).leave(_client_ip(request), screen_id, x_screen_secret)


@public_router.get(
    "/screens/{screen_id}/config",
    response_model=PublicScreenConfigOut,
    summary="公开大屏已发布配置",
)
def public_screen_config(
    screen_id: str, request: Request
) -> PublicScreenConfigOut:
    view = _screens(request).public_config(screen_id)
    return PublicScreenConfigOut(**asdict(view))


@public_router.get("/stream", summary="公开大屏 SSE")
def public_stream(request: Request, screen_id: str | None = None) -> StreamingResponse:
    bus = _bus(request)
    _ensure_stream_capacity(request)
    if screen_id:
        _screens(request).published_team_id(screen_id)
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
                views = request.app.state.container.tasks.list_tasks(owner_id=owner_id)
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
