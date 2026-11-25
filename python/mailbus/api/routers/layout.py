"""孪生布局路由（只读投影）。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import get_actor
from mailbus.api.mappers.layout import to_office_site_out, to_public_office_site_out
from mailbus.api.schemas.layout import OfficeSiteOut, PublicOfficeSiteOut

router = APIRouter(prefix="/api", tags=["layout"])


@router.get("/layout", response_model=OfficeSiteOut, summary="孪生办公室布局")
def get_layout(request: Request) -> OfficeSiteOut:
    get_actor(request)
    container = request.app.state.container
    return to_office_site_out(container.layout.get())


@router.get(
    "/public/layout", response_model=PublicOfficeSiteOut, summary="公开孪生布局（脱敏）"
)
def get_public_layout(
    request: Request, screen_id: str | None = Query(default=None)
) -> PublicOfficeSiteOut:
    """按屏幕已发布配置过滤团队；公开投影不含 team。"""
    container = request.app.state.container
    team_id = container.screens.published_team_id(screen_id) if screen_id else None
    return to_public_office_site_out(container.layout.get(team_id=team_id))
