"""system 路由：健康探测。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mailbus import __version__
from mailbus.api.schemas.system import HealthResponse

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="服务健康探测")
def health(request: Request) -> HealthResponse:
    container = request.app.state.container
    return HealthResponse(
        status="ok",
        service="mailbus",
        version=__version__,
        schema_version=container.schema_version,
        time=container.clock.now(),
    )
