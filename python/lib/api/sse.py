"""SSE（Server-Sent Events）通用支持层（PY4-A 双栈 SSE）。

协议（双栈一致，参照 device/chat 既有语义）：
    event: snapshot   data: {…}    —— 载荷变化时推（差量式）
    event: heartbeat  data: {…}    —— 无变化时的保活帧
    event: done       data: {…}    —— 正常结束
    event: error      data: {…}    —— 异常

响应头：text/event-stream + no-cache + Connection: close + X-Accel-Buffering: no。

并发护栏：python 服务每连接一线程（ThreadedHTTPServer，无池无上限），
SSE 长连接会独占线程且长期不释放——本模块用模块级计数器限制**同时在流**
的连接数，超限直接 503，避免线程被长连接无限占用。
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

# 同时在流的最大连接数（超出返 503）
MAX_ACTIVE_STREAMS = 8

_active_lock = threading.Lock()
_active_streams = 0


class StreamLimitExceeded(Exception):
    """并发流连接数超限。"""


def acquire_stream_slot() -> None:
    """占一个流连接名额；超限抛 StreamLimitExceeded。"""
    global _active_streams
    with _active_lock:
        if _active_streams >= MAX_ACTIVE_STREAMS:
            raise StreamLimitExceeded(
                f"too many concurrent streams (limit {MAX_ACTIVE_STREAMS})")
        _active_streams += 1


def release_stream_slot() -> None:
    """释放流连接名额。"""
    global _active_streams
    with _active_lock:
        if _active_streams > 0:
            _active_streams -= 1


def active_stream_count() -> int:
    """当前在流连接数（可观测）。"""
    with _active_lock:
        return _active_streams


def send_event(handler, event: str, data: Any) -> None:
    """推一帧 SSE（event 名 + JSON data）。"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    chunk = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
    handler.wfile.write(chunk)
    handler.wfile.flush()


def begin_stream(handler) -> None:
    """开始 SSE 响应（200 + 头）。"""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    # 一轮一答式流：结束即关；声明 close 让客户端明确响应边界
    # （HTTP/1.1 下无 Content-Length 会一直等）
    handler.send_header("Connection", "close")
    if hasattr(handler, "_apply_cors_headers"):
        handler._apply_cors_headers()
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()


def end_stream(handler) -> None:
    """结束 SSE 流：推 done 帧并关闭连接。"""
    try:
        send_event(handler, "done", {"status": "done"})
    except Exception:
        pass
    try:
        handler.wfile.flush()
    except Exception:
        pass
    handler.close_connection = True


def stream_snapshot(
    handler,
    loader: Callable[[], Any],
    *,
    poll_sec: float = 1.0,
    timeout_sec: float = 300.0,
    heartbeat_sec: float = 15.0,
    max_events: int = 0,
) -> None:
    """差量快照流：轮询 loader()，载荷变化才推 snapshot，无变化发心跳。

    参数语义沿用 a2a_stream 的配置模型（tick/timeout/heartbeat/max_events）：
    - poll_sec      轮询间隔
    - timeout_sec   流的绝对存活上限
    - heartbeat_sec 无变化时的保活间隔
    - max_events    最多推多少条 snapshot（0=不限）
    """
    deadline = time.monotonic() + max(0.0, timeout_sec)
    last_payload: Optional[str] = None
    last_beat = time.monotonic()
    events_sent = 0

    while True:
        if time.monotonic() >= deadline:
            return
        try:
            payload = loader()
        except Exception as exc:
            send_event(handler, "error", {"error": "stream_error", "message": str(exc)})
            return

        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if encoded != last_payload:
            send_event(handler, "snapshot", payload)
            last_payload = encoded
            events_sent += 1
            last_beat = time.monotonic()
            if max_events and events_sent >= max_events:
                return
        else:
            now = time.monotonic()
            if heartbeat_sec and (now - last_beat) >= heartbeat_sec:
                send_event(handler, "heartbeat", {"ts": time.time(), "events": events_sent})
                last_beat = now

        time.sleep(max(0.05, poll_sec))
