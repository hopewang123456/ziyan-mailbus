"""服务入口：``uvicorn mailbus.bootstrap.main:app``。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mailbus.api.app import build_app
from mailbus.api.body_limit import BodySizeLimitMiddleware
from mailbus.bootstrap.container import Container
from mailbus.bootstrap.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    container = Container(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await container.start()
        try:
            yield
        finally:
            await container.stop()

    app = build_app(lifespan=lifespan)
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=container.settings.max_body_bytes
    )
    app.state.container = container
    return app


app = create_app()
