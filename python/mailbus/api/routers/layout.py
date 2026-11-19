"""孪生布局路由（只读投影）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

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
def get_public_layout(request: Request) -> PublicOfficeSiteOut:
    """大屏公开投影：只保留姓名/岗位/团队/状态/任务，不含 agent_id 与心跳。"""
    container = request.app.state.container
    return to_public_office_site_out(container.layout.get())
