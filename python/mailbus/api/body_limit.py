"""请求体大小上限中间件（纯 ASGI，无第三方依赖）。

服务端没有文件上传接口，所有写路由都是 JSON；限制请求体可避免超大
载荷拖垮解析与内存。先看 Content-Length，缺失时按流式累计字节数兜底。
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

DEFAULT_MAX_BODY_BYTES = 1_048_576

_REJECT_BODY = json.dumps(
    {
        "error": "payload_too_large",
        "error_code": "payload_too_large",
        "message_zh": "请求体过大",
    },
    ensure_ascii=False,
).encode("utf-8")


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: Any, max_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await _reject(send)
            return
        state = {"total": 0, "started": False}

        async def limited_receive() -> dict[str, Any]:
            message = await receive()
            if message["type"] == "http.request":
                state["total"] += len(message.get("body", b""))
                if state["total"] > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                state["started"] = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            if not state["started"]:
                await _reject(send)


def _content_length(scope: dict[str, Any]) -> int | None:
    for name, value in scope.get("headers", ()):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _reject(send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(_REJECT_BODY)).encode("ascii")),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _REJECT_BODY})
