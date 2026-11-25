"""SSE 差量快照：overview 与最近日志共用，变化时才推送，其余时间心跳。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, AsyncIterator

from mailbus.core.shared.errors import CapacityError, PermissionDeniedError
from mailbus.core.shared.values import Capability

_LOG_LIMIT = 20
_HEARTBEAT_SEC = 15

# 公开流（未授权）事件白名单：只保留展示所需字段，剔除员工标识、task_id 等内部 ID。
# 未列出的事件种类在公开模式下直接丢弃，避免新增事件意外泄露。
_PUBLIC_EVENT_FIELDS: dict[str, tuple[str, ...]] = {
    "pair.started": ("pair_id", "at"),
    "pair.ended": ("pair_id", "at"),
    "message.created": ("message_id", "pair_id", "kind", "body", "created_at"),
    "task.updated": (
        "seat_id",
        "title",
        "state",
        "current_node",
        "node_state",
        "progress_done",
        "progress_total",
        "updated_at",
    ),
    "screen.config": ("screen_id", "config_version", "at"),
    "screen.focus": ("screen_id", "floor_id", "seat_id", "at"),
}


def _scrub_public(kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """返回公开安全的事件负载副本；未知事件返回 None（丢弃）。"""
    fields = _PUBLIC_EVENT_FIELDS.get(kind)
    if fields is None:
        return None
    return {key: payload[key] for key in fields if key in payload}


def snapshot(container: Any, actor: Any = None) -> dict[str, Any]:
    """运营快照；日志负载含全局事件，仅向具备 log_read 的账号下发。

    快照每秒重算，而响应头早已发出：若中途失去日志权限，宁可退化为「无日志」
    的降级快照，也不能让异常穿透到已开始的响应体（会变成 response already started）。
    """
    log: list[dict[str, Any]] = []
    if actor is not None and _can_read_log(actor):
        try:
            log = [asdict(entry) for entry in container.log.recent(actor, _LOG_LIMIT)]
        except PermissionDeniedError:
            log = []
    return {"overview": asdict(container.overview.get()), "log": log}


def _can_read_log(actor: Any) -> bool:
    capabilities = getattr(actor, "capabilities", frozenset())
    return Capability.ALL in capabilities or Capability.LOG_READ in capabilities


def _encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def event_stream(
    container: Any, actor: Any = None, interval: float = _HEARTBEAT_SEC
) -> AsyncIterator[str]:
    gate = container.stream_gate
    if not gate.acquire():
        raise CapacityError("事件流连接数已达上限，请稍后重试")
    try:
        last: str | None = None
        while True:
            payload = _encode(snapshot(container, actor))
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(interval)
    finally:
        gate.release()


async def collab_event_stream(
    bus: Any,
    *,
    screen_id: str | None = None,
    interval: float = _HEARTBEAT_SEC,
    public: bool = False,
) -> AsyncIterator[str]:
    """大屏事件流：``event: xxx`` + 单行 JSON，可选按 screen_id 过滤。

    心跳按绝对截止时间发送：持续收到其它大屏事件而被过滤时也要按时 ping，
    否则本连接会静默超过客户端的空闲看门狗阈值而被误判断线。

    ``public=True`` 时对事件负载按白名单脱敏，剔除员工标识与 task_id 等
    内部 ID（管理端流保持完整）。
    """
    async with bus.subscribe() as queue:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + interval
        while True:
            timeout = deadline - loop.time()
            if timeout <= 0:
                yield ": ping\n\n"
                deadline = loop.time() + interval
                continue
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                deadline = loop.time() + interval
                continue
            if screen_id is not None and payload.get("screen_id") != screen_id:
                continue
            if public:
                payload = _scrub_public(kind, payload)
                if payload is None:
                    continue
            deadline = loop.time() + interval
            yield f"event: {kind}\ndata: {_encode(payload)}\n\n"
