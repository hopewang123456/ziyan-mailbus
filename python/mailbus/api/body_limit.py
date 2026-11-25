"""请求体大小上限中间件（纯 ASGI，无第三方依赖）。

JSON 写路由用较小的 ``max_bytes``；multipart 产物上传单独放宽到
``multipart_bytes``，并由路由层再次做单文件上限校验。先看
Content-Length，缺失时按流式累计字节数兜底。
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

DEFAULT_MAX_BODY_BYTES = 1_048_576
DEFAULT_MULTIPART_BYTES = 100 * 1024 * 1024

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
    def __init__(self, app: Any, max_bytes: int = DEFAULT_MAX_BODY_BYTES,
                 multipart_bytes: int = DEFAULT_MULTIPART_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.multipart_bytes = multipart_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.multipart_bytes if _is_multipart(scope) else self.max_bytes
        declared = _content_length(scope)
        if declared is not None and declared > limit:
            await _reject(send)
            return
        state = {"total": 0, "started": False}

        async def limited_receive() -> dict[str, Any]:
            message = await receive()
            if message["type"] == "http.request":
                state["total"] += len(message.get("body", b""))
                if state["total"] > limit:
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


def _is_multipart(scope: dict[str, Any]) -> bool:
    for name, value in scope.get("headers", ()):
        if name == b"content-type" and value.lower().startswith(b"multipart/form-data"):
            return True
    return False


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
