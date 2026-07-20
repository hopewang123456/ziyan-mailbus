"""Google A2A JSON-RPC HTTP 客户端（SendMessage / SendStreamingMessage / GetTask / CancelTask）。"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from .a2a_mapper import to_a2a_message
from .errors import NonRetryableTransportError, RetryableTransportError, classify_http_status


def _parse_sse_jsonrpc_events(raw: str) -> list[dict]:
    """解析 SSE 流中 data: 行内的 JSON-RPC 响应。"""
    events: list[dict] = []
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line == "" and data_lines:
            blob = "".join(data_lines)
            data_lines = []
            try:
                events.append(json.loads(blob))
            except json.JSONDecodeError:
                continue
    if data_lines:
        try:
            events.append(json.loads("".join(data_lines)))
        except json.JSONDecodeError:
            pass
    return events


def _aggregate_streaming_result(events: list[dict]) -> dict[str, Any]:
    """将 SendStreamingMessage SSE 事件聚合为 SendMessage 兼容 result。"""
    task: dict[str, Any] = {}
    for ev in events:
        if ev.get("error"):
            err = ev["error"]
            code = str(err.get("code", ""))
            msg = err.get("message") or "rpc_error"
            if code in ("-32603", "503", "504") or "timeout" in msg.lower():
                raise RetryableTransportError(msg, code=code)
            raise NonRetryableTransportError(msg, code=code)
        result = ev.get("result")
        if not isinstance(result, dict):
            continue
        if result.get("id") and isinstance(result.get("status"), str):
            task = {**task, **result}
            continue
        tid = result.get("taskId") or result.get("task_id")
        st = result.get("status")
        if tid and isinstance(st, dict):
            state = st.get("state") or st.get("status") or ""
            task = {
                "id": tid,
                "status": state,
                "statusMessage": st.get("message") or task.get("statusMessage", ""),
            }
            if result.get("final"):
                break
        elif tid and isinstance(st, str):
            task = {"id": tid, "status": st}
    return {"task": task} if task.get("id") else {}


class HttpA2AClient:
    """对远端 Agent Card endpoint 发起 JSON-RPC 2.0 调用。"""

    def __init__(
        self,
        rpc_url: str,
        *,
        agent_id: str = "",
        auth_header: Optional[str] = None,
        timeout_sec: float = 60.0,
    ):
        self.rpc_url = rpc_url.rstrip("/")
        self.agent_id = agent_id
        self.auth_header = auth_header
        self.timeout_sec = timeout_sec
        self.task_id = ""
        self._resolve_sent = False

    @classmethod
    def from_agent_config(cls, agent_id: str, agent_cfg: dict, *, config: Optional[dict] = None) -> "HttpA2AClient":
        endpoint = (agent_cfg or {}).get("endpoint") or {}
        card = (agent_cfg or {}).get("agent_card") or (agent_cfg or {}).get("wire") or {}
        interfaces = card.get("supportedInterfaces") or (agent_cfg or {}).get("supportedInterfaces") or []
        rpc_url = endpoint.get("rpc_url") or endpoint.get("base_url") or ""
        if not rpc_url and interfaces:
            rpc_url = (interfaces[0] or {}).get("url") or ""
        if not rpc_url:
            raise NonRetryableTransportError(f"no rpc url for agent {agent_id}", code="no_endpoint")
        auth = None
        scheme = ((agent_cfg or {}).get("auth") or {}).get("scheme", "")
        token_env = ((agent_cfg or {}).get("auth") or {}).get("token_env", "")
        if scheme == "bearer" and token_env:
            import os

            tok = os.environ.get(token_env, "")
            if tok:
                auth = f"Bearer {tok}"
        tc = (config or {}).get("transport") or {}
        timeout = float(tc.get("http_timeout_sec") or 60)
        return cls(rpc_url, agent_id=agent_id, auth_header=auth, timeout_sec=timeout)

    def _rpc(self, method: str, params: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        req = urlrequest.Request(self.rpc_url, data=data, headers=headers, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=self.timeout_sec) as resp:
                body = resp.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            raise classify_http_status(exc.code) from exc
        except urlerror.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if "timed out" in str(reason).lower():
                raise RetryableTransportError("timeout", code="timeout") from exc
            raise RetryableTransportError(str(reason), code="network") from exc

        try:
            doc = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NonRetryableTransportError("invalid_json_response", code="parse") from exc
        if doc.get("error"):
            err = doc["error"]
            code = str(err.get("code", ""))
            msg = err.get("message") or "rpc_error"
            if code in ("-32603", "503", "504") or "timeout" in msg.lower():
                raise RetryableTransportError(msg, code=code)
            raise NonRetryableTransportError(msg, code=code)
        return doc.get("result") or {}

    def _rpc_sse(self, method: str, params: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        req = urlrequest.Request(self.rpc_url, data=data, headers=headers, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=self.timeout_sec) as resp:
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            raise classify_http_status(exc.code) from exc
        except urlerror.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if "timed out" in str(reason).lower():
                raise RetryableTransportError("timeout", code="timeout") from exc
            raise RetryableTransportError(str(reason), code="network") from exc

        if "text/event-stream" in ctype:
            events = _parse_sse_jsonrpc_events(body)
            result = _aggregate_streaming_result(events)
            if not result.get("task"):
                raise NonRetryableTransportError("empty_stream", code="parse")
            return result

        try:
            doc = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NonRetryableTransportError("invalid_json_response", code="parse") from exc
        if doc.get("error"):
            err = doc["error"]
            code = str(err.get("code", ""))
            msg = err.get("message") or "rpc_error"
            if code in ("-32603", "503", "504") or "timeout" in msg.lower():
                raise RetryableTransportError(msg, code=code)
            raise NonRetryableTransportError(msg, code=code)
        return doc.get("result") or {}

    def send_message(self, dispatch: dict[str, Any]) -> dict[str, Any]:
        message = to_a2a_message(dispatch)
        message.setdefault("messageId", str(uuid.uuid4()))
        result = self._rpc("SendMessage", {"message": message})
        task = result.get("task") or {}
        self.task_id = task.get("id") or self.task_id
        return result

    def send_resolve(self, resolve_msg: dict[str, Any]) -> dict[str, Any]:
        params = resolve_msg if "message" in resolve_msg else {"message": resolve_msg.get("message")}
        if resolve_msg.get("taskId"):
            params = dict(params)
            params["taskId"] = resolve_msg["taskId"]
        result = self._rpc("SendMessage", params)
        self._resolve_sent = True
        task = result.get("task") or {}
        self.task_id = task.get("id") or self.task_id
        return result

    def send_streaming_message(self, dispatch: dict[str, Any]) -> dict[str, Any]:
        """SendStreamingMessage via SSE；远端不支持时回落 SendMessage。"""
        message = to_a2a_message(dispatch)
        message.setdefault("messageId", str(uuid.uuid4()))
        try:
            result = self._rpc_sse("SendStreamingMessage", {"message": message})
        except NonRetryableTransportError as exc:
            if exc.code in ("-32601", "404") or "not found" in str(exc).lower():
                return self.send_message(dispatch)
            raise
        task = result.get("task") or {}
        self.task_id = task.get("id") or self.task_id
        return result

    def poll_task(self) -> dict[str, Any]:
        if not self.task_id:
            return {"id": "", "status": "failed", "statusMessage": "missing task id"}
        result = self._rpc("GetTask", {"id": self.task_id})
        task = result.get("task") or result
        task.setdefault("id", self.task_id)
        return task

    def cancel_task(self, a2a_task_id: Optional[str] = None) -> dict[str, Any]:
        tid = a2a_task_id or self.task_id
        if not tid:
            return {"ok": False, "error": "missing task id"}
        try:
            return self._rpc("CancelTask", {"id": tid})
        except NonRetryableTransportError:
            return {"ok": False, "id": tid, "cancelled": False}

    def mark_resolved(self) -> None:
        self._resolve_sent = True

    def is_terminal(self, task: dict[str, Any]) -> bool:
        return (task.get("status") or "").lower() in (
            "completed", "failed", "canceled", "cancelled",
        )
