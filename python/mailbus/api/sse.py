"""SSE 差量快照：overview 与最近日志共用，变化时才推送，其余时间心跳。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, AsyncIterator

_LOG_LIMIT = 20
_HEARTBEAT_SEC = 15


def snapshot(container: Any) -> dict[str, Any]:
    return {
        "overview": asdict(container.overview.get()),
        "log": [asdict(entry) for entry in container.log.recent(_LOG_LIMIT)],
    }


def _encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def event_stream(
    container: Any, interval: float = _HEARTBEAT_SEC
) -> AsyncIterator[str]:
    last: str | None = None
    while True:
        payload = _encode(snapshot(container))
        if payload != last:
            yield f"data: {payload}\n\n"
            last = payload
        else:
            yield ": heartbeat\n\n"
        await asyncio.sleep(interval)


async def collab_event_stream(
    bus: Any,
    *,
    screen_id: str | None = None,
    interval: float = _HEARTBEAT_SEC,
) -> AsyncIterator[str]:
    """大屏事件流：``event: xxx`` + 单行 JSON，可选按 screen_id 过滤。"""
    async with bus.subscribe() as queue:
        while True:
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if screen_id is not None and payload.get("screen_id") != screen_id:
                continue
            yield f"event: {kind}\ndata: {_encode(payload)}\n\n"
