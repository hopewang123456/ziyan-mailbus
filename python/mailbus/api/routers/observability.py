"""运营观测路由：总览、操作日志与 SSE 差量流。"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from mailbus.api import sse
from mailbus.api.deps import get_actor
from mailbus.api.schemas.observability import LogEntryOut, OverviewOut
from mailbus.core.shared.errors import CapacityError

router = APIRouter(prefix="/api", tags=["observability"])


@router.get("/overview", response_model=OverviewOut, summary="运营总览")
def get_overview(request: Request) -> OverviewOut:
    get_actor(request)
    return OverviewOut(**asdict(request.app.state.container.overview.get()))


@router.get("/log", response_model=list[LogEntryOut], summary="操作日志")
def list_log(
    request: Request, limit: int = Query(default=50, ge=1, le=500)
) -> list[LogEntryOut]:
    actor = get_actor(request)
    entries = request.app.state.container.log.recent(actor, limit)
    return [
        LogEntryOut(
            event_id=entry.event_id,
            kind=entry.kind,
            payload=entry.payload,
            attempts=entry.attempts,
            created_at=entry.created_at,
        )
        for entry in entries
    ]


@router.get("/stream", summary="运营事件流（SSE）")
def stream(request: Request) -> StreamingResponse:
    actor = get_actor(request)
    container = request.app.state.container
    if container.stream_gate.full:
        raise CapacityError("事件流连接数已达上限，请稍后重试")
    return StreamingResponse(
        sse.event_stream(container, actor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
