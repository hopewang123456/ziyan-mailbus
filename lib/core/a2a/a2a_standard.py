"""Google A2A JSON-RPC 传输（含 stub 注入）。"""
from __future__ import annotations

import os
from typing import Any, Optional

from lib.infra.utils import json_read
from .a2a_mapper import from_a2a_task, to_a2a_resolve_message
from .errors import NonRetryableTransportError, TransportError
from .stub_a2a import StubA2AClient
from .types import DispatchContext


class A2ATransport:
    def __init__(self, rpc: Any = None, *, config: Optional[dict] = None, data_dir: str = ""):
        self.rpc = rpc
        self.config = config or {}
        self.data_dir = data_dir

    def dispatch_once(self, ctx: DispatchContext, agents: dict) -> dict[str, Any]:
        """SendMessage 或 SendStreamingMessage + 轮询至 terminal 或 input-required。"""
        client = self._client(ctx, agents)
        task_id, first_task = self._send_only(client, ctx, prefer_streaming=self._use_streaming(ctx, agents))
        return self._poll_to_outcome(client, ctx, task_id, first_task=first_task)

    def dispatch_async(self, ctx: DispatchContext, agents: dict) -> dict[str, Any]:
        """SendMessage 或 SendStreamingMessage（use_streaming 时），供 scanner 后续轮询。"""
        client = self._client(ctx, agents)
        task_id, _ = self._send_only(client, ctx, prefer_streaming=self._use_streaming(ctx, agents))
        return {"ok": True, "a2a_task_id": task_id}

    def poll_task(self, ctx: DispatchContext, a2a_task_id: str, *, client: Any = None, agents: Optional[dict] = None) -> dict[str, Any]:
        client = client or self._client(ctx, agents or {})
        client.task_id = a2a_task_id
        task = client.poll_task()
        return self._poll_to_outcome(client, ctx, a2a_task_id, first_task=task)

    def resume_after_resolve(
        self,
        ctx: DispatchContext,
        *,
        a2a_task_id: str,
        agent_id: str,
        display_name: str,
        role_type: int,
        comment: str,
        hq_id: str = "",
        hq_type: str = "a2a_input_required",
        agents: Optional[dict] = None,
    ) -> dict[str, Any]:
        client = self._client(ctx, agents or {})
        client.task_id = a2a_task_id
        resolve_msg = to_a2a_resolve_message(
            task_id=ctx.task_id,
            step_id=ctx.step_id,
            agent_id=agent_id,
            display_name=display_name,
            role_type=role_type,
            comment=comment,
            hq_id=hq_id,
            hq_type=hq_type,
            a2a_task_id=a2a_task_id,
        )
        if hasattr(client, "send_resolve"):
            client.send_resolve(resolve_msg)
        else:
            client.mark_resolved()
        return self._poll_to_outcome(client, ctx, a2a_task_id)

    def cancel_task(
        self,
        ctx: DispatchContext,
        a2a_task_id: str,
        agents: dict,
    ) -> dict[str, Any]:
        client = self._client(ctx, agents)
        if hasattr(client, "cancel_task"):
            return client.cancel_task(a2a_task_id)
        return {"ok": False, "error": "cancel_not_supported"}

    def _use_streaming(self, ctx: DispatchContext, agents: dict) -> bool:
        from .config import resolve_use_streaming

        agent_cfg = (agents or {}).get(ctx.to_agent) or {}
        return resolve_use_streaming(self.config, agent_cfg)

    def _send_only(
        self,
        client: Any,
        ctx: DispatchContext,
        *,
        prefer_streaming: bool = False,
    ) -> tuple[str, Optional[dict]]:
        dispatch = {
            "task_id": ctx.task_id,
            "step_id": ctx.step_id,
            "to_agent": ctx.to_agent,
            "role_type": ctx.role_type,
            "intent": ctx.intent,
            "msg_file": ctx.msg_file,
        }
        sent: dict[str, Any]
        if prefer_streaming and hasattr(client, "send_streaming_message"):
            try:
                sent = client.send_streaming_message(dispatch)
            except NonRetryableTransportError as exc:
                code = str(exc.code or "")
                if code in ("-32601", "404", "empty_stream", "parse") or "not found" in str(exc).lower():
                    sent = client.send_message(dispatch)
                else:
                    raise
            except TransportError:
                raise
        else:
            try:
                sent = client.send_message(dispatch)
            except TransportError:
                raise
        task = sent.get("task") or {}
        task_id = task.get("id") or getattr(client, "task_id", "")
        return task_id, task or None

    def _poll_to_outcome(
        self,
        client: Any,
        ctx: DispatchContext,
        task_id: str,
        *,
        first_task: Optional[dict] = None,
    ) -> dict[str, Any]:
        import time

        poll_cfg = (self.config.get("transport") or {}).get("a2a") or self.config.get("a2a") or {}
        poll_interval = float(poll_cfg.get("poll_interval_sec") or 0)
        max_polls = int(poll_cfg.get("max_polls") or 120)
        task = first_task or client.poll_task()
        polls = 0
        while not client.is_terminal(task):
            status = (task.get("status") or "").lower()
            if status == "input-required":
                return {
                    "ok": False,
                    "awaiting_human": True,
                    "a2a_task_id": task_id,
                    "task": task,
                    "human_queue": {
                        "type": "a2a_input_required",
                        "task_id": ctx.task_id,
                        "title": f"{ctx.to_agent} 需确认",
                        "context": {
                            "step_id": ctx.step_id,
                            "a2a_task_id": task_id,
                            "prompt": task.get("statusMessage") or "",
                            "role_type": ctx.role_type,
                            "to_agent": ctx.to_agent,
                        },
                    },
                }
            polls += 1
            if polls >= max_polls:
                break
            if poll_interval > 0:
                time.sleep(poll_interval)
            task = client.poll_task()
        step_result = from_a2a_task(
            task,
            task_id=ctx.task_id,
            step_id=ctx.step_id,
            agent=ctx.to_agent,
            role_type=ctx.role_type,
        )
        return {
            "ok": True,
            "a2a_task_id": task_id,
            "task": task,
            "step_result": step_result,
        }

    def _client(self, ctx: DispatchContext, agents: dict) -> Any:
        if self.rpc is not None:
            return self.rpc
        cfg = self.config
        if not cfg and self.data_dir:
            cfg = json_read(os.path.join(self.data_dir, "config.json"), {})
        if not cfg and ctx.data_dir:
            cfg = json_read(os.path.join(ctx.data_dir, "config.json"), {})
        harness_mode = (cfg.get("harness") or {}).get("mode", "production")
        transport_cfg = cfg.get("transport") or cfg
        force_stub = transport_cfg.get("force_stub")
        if harness_mode == "stub" or force_stub:
            name = ctx.stub_fixture or "path-a-lingzhao-s1.json"
            if ctx.to_agent == "dali":
                name = ctx.stub_fixture or "path-d-dali-opencode.json"
            return StubA2AClient.from_name(name)
        agent_cfg = (agents or {}).get(ctx.to_agent) or {}
        from .delivery import can_deliver_a2a
        from .http_a2a import HttpA2AClient

        if can_deliver_a2a(ctx.to_agent, agent_cfg, ctx):
            try:
                return HttpA2AClient.from_agent_config(ctx.to_agent, agent_cfg, config=cfg)
            except TransportError:
                raise
            except Exception as exc:
                from .errors import NonRetryableTransportError
                raise NonRetryableTransportError(str(exc), code="http_client") from exc
        name = ctx.stub_fixture or "path-a-lingzhao-s1.json"
        return StubA2AClient.from_name(name)
