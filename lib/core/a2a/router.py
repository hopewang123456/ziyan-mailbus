"""双通道 Transport Router。"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from lib.application.orchestration.pipeline.results import step_result_path
from lib.infra.utils import _now_iso, json_read
from .step_result_io import read_step_result_file, write_step_result_file
from .a2a_standard import A2ATransport
from .config import load_transport_config
from .delivery import can_deliver_a2a, persist_step_transport
from .errors import NonRetryableTransportError, RetryableTransportError, TransportError
from .fallback_log import log_a2a_fallback
from .file_bus import FileBusTransport
from .types import DispatchContext, DispatchResult


class TransportRouter:
    def __init__(
        self,
        *,
        data_dir: str = "",
        config: Optional[dict] = None,
        a2a: Optional[A2ATransport] = None,
        file_bus: Optional[FileBusTransport] = None,
    ):
        self.data_dir = data_dir
        store_cfg = config or json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else (config or {})
        self.config = load_transport_config(store_cfg, data_dir=data_dir)
        harness_mode = (store_cfg.get("harness") or {}).get("mode", "production")
        self.a2a = a2a or A2ATransport(config=store_cfg, data_dir=data_dir)
        self.file_bus = file_bus or FileBusTransport(mode=harness_mode)

    def can_deliver_a2a(self, agent_id: str, agents: dict, ctx: DispatchContext) -> bool:
        return can_deliver_a2a(agent_id, agents.get(agent_id) or {}, ctx)

    def dispatch_step(self, ctx: DispatchContext, agents: Optional[dict] = None) -> DispatchResult:
        agents = agents or self._agents(ctx.data_dir)
        attempts: list[dict[str, Any]] = []
        policy = ctx.transport_policy or {}
        max_retries = int(policy.get("max_retries") or (self.config.get("a2a") or {}).get("max_retries", 3))
        backoff = list((self.config.get("a2a") or {}).get("retry_backoff_sec") or [2, 5, 10])

        if not self.can_deliver_a2a(ctx.to_agent, agents, ctx):
            return self._file_bus_finish(ctx, agents, attempts, exhausted=False)

        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                outcome = self.a2a.dispatch_once(ctx, agents)
                if outcome.get("awaiting_human"):
                    attempts.append({
                        "channel": "a2a_standard",
                        "attempt": attempt,
                        "outcome": "input_required",
                        "ts": _now_iso(),
                    })
                    persist_step_transport(
                        ctx.data_dir, ctx,
                        transport_used="a2a_standard",
                        transport_attempts=attempts,
                        a2a_task_id=outcome.get("a2a_task_id"),
                    )
                    hq_payload = outcome.get("human_queue")
                    if hq_payload:
                        from lib.adapters.orchestration.human_queue import enqueue

                        hq_payload = dict(hq_payload)
                        hq_payload.setdefault("task_id", ctx.task_id)
                        enqueue(ctx.data_dir, hq_payload)
                    return DispatchResult(
                        ok=False,
                        transport_used="a2a_standard",
                        a2a_task_id=outcome.get("a2a_task_id"),
                        transport_attempts=attempts,
                        awaiting_human=True,
                        human_queue_payload=outcome.get("human_queue"),
                    )
                if outcome.get("ok"):
                    step_result = outcome["step_result"]
                    write_step_result_file(
                        ctx.data_dir, ctx.task_id, ctx.step_id, step_result,
                        agent=ctx.to_agent, role_type=ctx.role_type,
                    )
                    attempts.append({
                        "channel": "a2a_standard",
                        "attempt": attempt,
                        "outcome": "ok",
                        "ts": _now_iso(),
                    })
                    persist_step_transport(
                        ctx.data_dir, ctx,
                        transport_used="a2a_standard",
                        transport_attempts=attempts,
                        a2a_task_id=outcome.get("a2a_task_id"),
                    )
                    return DispatchResult(
                        ok=True,
                        transport_used="a2a_standard",
                        a2a_task_id=outcome.get("a2a_task_id"),
                        step_result_path=step_result_path(ctx.data_dir, ctx.task_id, ctx.step_id),
                        transport_attempts=attempts,
                    )
            except NonRetryableTransportError as exc:
                last_error = str(exc)
                attempts.append({
                    "channel": "a2a_standard",
                    "attempt": attempt,
                    "outcome": "fail",
                    "error": last_error,
                    "ts": _now_iso(),
                })
                break
            except (RetryableTransportError, TransportError) as exc:
                last_error = str(exc)
                attempts.append({
                    "channel": "a2a_standard",
                    "attempt": attempt,
                    "outcome": "fail",
                    "error": last_error,
                    "ts": _now_iso(),
                })
                if attempt < max_retries:
                    delay = backoff[min(attempt - 1, len(backoff) - 1)]
                    time.sleep(delay)

        return self._file_bus_finish(ctx, agents, attempts, exhausted=True, last_error=last_error)

    def _file_bus_finish(
        self,
        ctx: DispatchContext,
        agents: dict,
        attempts: list[dict[str, Any]],
        *,
        exhausted: bool,
        last_error: str = "",
    ) -> DispatchResult:
        fb = self.file_bus.dispatch(ctx, agents)
        attempts.append({
            "channel": "file_bus",
            "attempt": 1,
            "outcome": "ok" if fb.ok else "fail",
            "fallback_from": "a2a_standard" if exhausted else None,
            "ts": _now_iso(),
        })
        if exhausted and self.config.get("fallback_alerts", {}).get("enabled", True):
            log_a2a_fallback(ctx.data_dir, ctx, attempts, last_error=last_error)
        persist_step_transport(
            ctx.data_dir, ctx,
            transport_used="file_bus",
            transport_attempts=attempts,
            a2a_retries_exhausted=exhausted,
        )
        fb.transport_attempts = attempts
        fb.a2a_retries_exhausted = exhausted
        return fb

    def _agents(self, data_dir: str) -> dict:
        return json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}
