"""FastAPI 应用装配（不依赖 bootstrap，便于组合根注入 lifespan）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mailbus import __version__
from mailbus.api.errors import register_error_handlers
from mailbus.api.routers import (
    a2a,
    agent_invites,
    agents,
    approval,
    audit,
    collab,
    identity,
    integrations,
    layout,
    mcp,
    messages,
    metrics,
    observability,
    org_employees,
    org_invites,
    org_positions,
    org_roles,
    skills,
    system,
    tasks,
    workflow,
)


def build_app(lifespan: Any = None, web_dist: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="mailbus",
        version=__version__,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(system.router)
    app.include_router(identity.router)
    app.include_router(agents.router)
    app.include_router(agent_invites.router)
    app.include_router(org_employees.router)
    app.include_router(org_invites.router)
    app.include_router(org_positions.router)
    app.include_router(org_roles.router)
    app.include_router(layout.router)
    app.include_router(workflow.router)
    app.include_router(tasks.router)
    app.include_router(tasks.artifact_router)
    app.include_router(approval.router)
    app.include_router(messages.router)
    app.include_router(skills.router)
    app.include_router(metrics.router)
    app.include_router(audit.router)
    app.include_router(integrations.router)
    app.include_router(a2a.router)
    app.include_router(mcp.router)
    app.include_router(observability.router)
    app.include_router(collab.router)
    app.include_router(collab.public_router)
    if web_dist is not None:
        _mount_web(app, Path(web_dist))
    return app


def _mount_web(app: FastAPI, dist: Path) -> None:
    """同源托管 web 构建产物（默认 <仓库根>/web/dist，存在才挂载）。

    /api 前缀仍走 API 路由；其余路径优先命中静态文件，否则回退 index.html
    以支持前端路由。路径越界一律拒绝。
    """
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"MAILBUS_WEB_DIST 缺少 index.html：{dist}")
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="web-assets")
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def web_spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        if full_path:
            candidate = (root / full_path).resolve()
            if root in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index)
