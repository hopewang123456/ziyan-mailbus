"""FastAPI 应用装配（不依赖 bootstrap，便于组合根注入 lifespan）。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from mailbus import __version__
from mailbus.api.errors import register_error_handlers
from mailbus.api.routers import (
    a2a,
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
    org,
    skills,
    system,
    tasks,
    workflow,
)


def build_app(lifespan: Any = None) -> FastAPI:
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
    app.include_router(org.router)
    app.include_router(layout.router)
    app.include_router(workflow.router)
    app.include_router(tasks.router)
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
    return app
