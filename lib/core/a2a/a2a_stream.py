"""入站 SendStreamingMessage：按 FSM 轮询推送 TaskStatusUpdateEvent。"""
from __future__ import annotations

import os
import time
from typing import Any, Iterator, Optional

from .config import load_transport_config

_STREAM_TERMINAL = frozenset({
    "completed", "failed", "canceled", "cancelled", "input-required",
})


def is_stream_terminal(status: str) -> bool:
    return (status or "").lower() in _STREAM_TERMINAL


def build_status_update_result(a2a_task_id: str, hub_wire: dict, *, final: bool) -> dict[str, Any]:
    """TaskStatusUpdateEvent → JSON-RPC result 片段。"""
    return {
        "taskId": a2a_task_id,
        "status": {
            "state": hub_wire.get("status") or "working",
            "message": hub_wire.get("statusMessage") or "",
        },
        "final": final,
    }


def resolve_hub_wire(
    data_dir: str,
    mailbus_task_id: str,
    a2a_task_id: str,
) -> Optional[dict[str, Any]]:
    from lib.adapters.orchestration.human_queue import load_queue
    from lib.application.orchestration.tracker import TaskTracker
    from .a2a_mapper import to_a2a_hub_task

    task_doc = TaskTracker(data_dir).get(mailbus_task_id)
    if not task_doc:
        return None
    hq_items = load_queue(data_dir).get("items") or []
    return to_a2a_hub_task(task_doc, a2a_task_id, human_queue=hq_items)


def _stream_config(data_dir: str) -> dict[str, float | int]:
    cfg = load_transport_config(data_dir=data_dir)
    a2a = cfg.get("a2a") or {}
    tick = max(float(a2a.get("stream_poll_sec") or 0.1), 0.05)
    return {
        "tick": tick,
        "timeout": max(float(a2a.get("stream_timeout_sec") or 120), 1.0),
        "heartbeat": max(float(a2a.get("stream_heartbeat_sec") or 15), 0.0),
        "max_events": max(int(a2a.get("stream_max_events") or 0), 0),
        "missing_grace": max(float(a2a.get("stream_missing_grace_sec") or 0.3), tick),
    }


def _maybe_advance_a2a(data_dir: str, agents: dict, paths: Optional[dict]) -> None:
    if not paths:
        return
    try:
        from lib.application.orchestration.a2a_poll import poll_pending_a2a_tasks

        poll_pending_a2a_tasks(data_dir, agents or {}, paths)
    except Exception:
        pass


def _timeout_hub(hub: dict[str, Any]) -> dict[str, Any]:
    msg = hub.get("statusMessage") or ""
    return {**hub, "statusMessage": f"{msg} (stream timeout)".strip()}


def iter_stream_events(
    data_dir: str,
    wire_task: dict,
    *,
    agents: Optional[dict] = None,
    paths: Optional[dict] = None,
    tick_sec: Optional[float] = None,
    timeout_sec: Optional[float] = None,
) -> Iterator[dict[str, Any]]:
    """轮询 FSM；yield ``{"kind": "heartbeat"}`` 或 ``{"kind": "update", "hub", "final"}``。"""
    meta = (wire_task.get("metadata") or {}).get("mailbus") or {}
    mailbus_task_id = meta.get("taskId") or ""
    a2a_task_id = wire_task.get("id") or ""
    if not mailbus_task_id:
        return

    cfg = _stream_config(data_dir)
    tick = cfg["tick"] if tick_sec is None else max(float(tick_sec), 0.05)
    timeout = cfg["timeout"] if timeout_sec is None else max(float(timeout_sec), 1.0)
    heartbeat_sec = float(cfg["heartbeat"])
    max_events = int(cfg["max_events"])
    missing_grace = float(cfg["missing_grace"])
    if paths is None and data_dir:
        paths = {"inbox": os.path.join(data_dir, "inbox")}

    last_status = (wire_task.get("status") or "working").lower()
    deadline = time.monotonic() + timeout
    missing_deadline: Optional[float] = None
    next_heartbeat = time.monotonic() + heartbeat_sec if heartbeat_sec > 0 else None
    event_count = 0

    def _emit_update(hub: dict[str, Any], *, final: bool) -> Iterator[dict[str, Any]]:
        nonlocal last_status, event_count, next_heartbeat
        status = (hub.get("status") or "working").lower()
        last_status = status
        event_count += 1
        yield {"kind": "update", "hub": hub, "final": final}
        if heartbeat_sec > 0:
            next_heartbeat = time.monotonic() + heartbeat_sec

    while time.monotonic() < deadline:
        _maybe_advance_a2a(data_dir, agents or {}, paths)
        hub = resolve_hub_wire(data_dir, mailbus_task_id, a2a_task_id)
        if not hub:
            if missing_deadline is None:
                missing_deadline = time.monotonic() + missing_grace
            elif time.monotonic() >= missing_deadline:
                return
        else:
            missing_deadline = None
            status = (hub.get("status") or "working").lower()
            if status != last_status:
                final = is_stream_terminal(status)
                yield from _emit_update(hub, final=final)
                if final:
                    return
                if max_events and event_count >= max_events:
                    yield from _emit_update(_timeout_hub(hub), final=True)
                    return
            elif is_stream_terminal(status):
                return

        now = time.monotonic()
        if next_heartbeat is not None and now >= next_heartbeat:
            yield {"kind": "heartbeat"}
            next_heartbeat = now + heartbeat_sec

        time.sleep(tick)

    hub = resolve_hub_wire(data_dir, mailbus_task_id, a2a_task_id)
    if hub and not is_stream_terminal(hub.get("status") or ""):
        yield from _emit_update(_timeout_hub(hub), final=True)


def iter_stream_status_updates(
    data_dir: str,
    wire_task: dict,
    *,
    agents: Optional[dict] = None,
    paths: Optional[dict] = None,
    tick_sec: Optional[float] = None,
    timeout_sec: Optional[float] = None,
) -> Iterator[tuple[dict[str, Any], bool]]:
    """状态变化时 yield (hub_wire, is_final)；不含首帧 working Task。"""
    for event in iter_stream_events(
        data_dir,
        wire_task,
        agents=agents,
        paths=paths,
        tick_sec=tick_sec,
        timeout_sec=timeout_sec,
    ):
        if event.get("kind") == "update":
            yield event["hub"], event["final"]


def aggregate_stream_task(
    data_dir: str,
    wire_task: dict,
    rpc_id: Any,
    *,
    agents: Optional[dict] = None,
    paths: Optional[dict] = None,
    tick_sec: Optional[float] = None,
    timeout_sec: Optional[float] = None,
) -> dict[str, Any]:
    """Accept: application/json 时聚合 SSE 事件为 terminal Task。"""
    from .http_a2a import _aggregate_streaming_result

    a2a_task_id = wire_task.get("id") or ""
    events: list[dict] = [{"jsonrpc": "2.0", "id": rpc_id, "result": wire_task}]
    for hub, is_final in iter_stream_status_updates(
        data_dir,
        wire_task,
        agents=agents,
        paths=paths,
        tick_sec=tick_sec,
        timeout_sec=timeout_sec,
    ):
        events.append({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": build_status_update_result(a2a_task_id, hub, final=is_final),
        })
        if is_final:
            break
    out = _aggregate_streaming_result(events)
    return out.get("task") or wire_task
