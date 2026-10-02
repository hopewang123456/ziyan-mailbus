"""file_bus 通道 — stub 直写 step-result；生产路径写 inbox + Harness wait。"""
from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.pipeline_results import step_result_path  # 2026-09 治理下沉
from .step_result_io import write_step_result_file
from lib.infra.utils import json_write, json_read, jsonl_append, _now_iso
from .types import DispatchContext, DispatchResult


def _load_stub_fixture(name: str) -> dict[str, Any]:
    base = os.path.join(str(MAILBUS_ROOT), "tests", "fixtures", "harness_stub")
    path = name if name.endswith(".json") else f"{name}.json"
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class FileBusTransport:
    def __init__(self, *, harness: Any = None, mode: str = "production"):
        self.harness = harness
        self.mode = mode

    def dispatch(self, ctx: DispatchContext, agents: dict) -> DispatchResult:
        fixture_name = ctx.stub_fixture
        if self.mode == "stub" or fixture_name:
            return self._dispatch_stub(ctx, fixture_name)
        return self._dispatch_production(ctx, agents)

    def _wait_timeout_sec(self, data_dir: str) -> int:
        cfg = json_read(os.path.join(data_dir, "config.json"), {})
        harness_cfg = cfg.get("harness") or {}
        fb = harness_cfg.get("file_bus") or {}
        if fb.get("ack_timeout_sec"):
            return int(fb["ack_timeout_sec"])
        return int(cfg.get("ack_timeout") or 300)

    def _wait_on_dispatch(self, data_dir: str) -> bool:
        """P10：派发默认「投递即返回」，同步等执行结果改为 opt-in。"""
        cfg = json_read(os.path.join(data_dir, "config.json"), {})
        fb = (cfg.get("harness") or {}).get("file_bus") or {}
        return bool(fb.get("wait_on_dispatch"))

    def _audit_wait_timeout(
        self,
        ctx: DispatchContext,
        msg_id: str,
        *,
        ack_received: bool,
        error: str,
    ) -> None:
        errors_dir = os.path.join(ctx.data_dir, "errors")
        os.makedirs(errors_dir, exist_ok=True)
        dt = now_utc_dt()
        week = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        path = os.path.join(errors_dir, f"file-bus-wait-{week}.jsonl")
        jsonl_append(path, {
            "event": "file_bus_wait_timeout",
            "task_id": ctx.task_id,
            "step_id": ctx.step_id,
            "to_agent": ctx.to_agent,
            "msg_id": msg_id,
            "ack_received": ack_received,
            "error": error,
            "ts": _now_iso(),
            "notify": ["dashboard", "ops_inbox"],
        })

    def _dispatch_production(self, ctx: DispatchContext, agents: dict) -> DispatchResult:
        inbox_dir = os.path.join(ctx.data_dir, "inbox", ctx.to_agent)
        os.makedirs(inbox_dir, exist_ok=True)
        msg_id = f"msg-{ctx.task_id}-{ctx.step_id}"
        inbox_path = os.path.join(inbox_dir, "inbox.json")
        inbox = {"agent": ctx.to_agent, "messages": []}
        if os.path.isfile(inbox_path):
            with open(inbox_path, encoding="utf-8") as f:
                inbox = json.load(f)
        inbox.setdefault("messages", []).append({
            "id": msg_id,
            "from": "mailbus",
            "to": ctx.to_agent,
            "type": "task",
            "state": "pending",
            "task_id": ctx.task_id,
            "step_id": ctx.step_id,
            "content": ctx.intent or f"【{ctx.task_id}】step {ctx.step_id}",
            "created_at": _now_iso(),
        })
        json_write(inbox_path, inbox)

        if self.harness is None:
            return DispatchResult(
                ok=True,
                transport_used="file_bus",
                error=None,
            )

        agent_cfg = (agents or {}).get(ctx.to_agent) or {}
        session = self.harness.spawn(ctx.to_agent, {
            "data_dir": ctx.data_dir,
            "task_id": ctx.task_id,
            "step_id": ctx.step_id,
            "msg_id": msg_id,
            # P10：工单内容必须进 prompt——spawn 出的 CLI 只拿 contract 摘要时，
            # agent 收到的是「怎么回执」而不是「做什么」。
            "prompt": ctx.intent or f"【{ctx.task_id}】step {ctx.step_id}",
            "framework": agent_cfg.get("type") or "",
            "transport_channel": "file_bus",
        })
        # M2：首派 spawn 即占住推送槽（state=pushed）——scan 不再二次推送同一条
        # 消息（game 实验实锤的「首派 spawn + scan 二次推送重复消费」）。
        # CLI 死亡无回执时由 recover_inbox_stale_states 僵尸回收回 pending 重推，
        # 语义仍为 at-least-once；spawn 抛错则不标记，scan 是兜底推送方。
        self._mark_inbox_dispatched(inbox_path, msg_id)
        if not self._wait_on_dispatch(ctx.data_dir):
            # P10：投递语义 at-least-once——inbox 落盘 + spawn 通知即成功；
            # 执行结果由 scan/trigger 异步消化（派发不再同步阻塞 ack_timeout）。
            return DispatchResult(
                ok=True,
                transport_used="file_bus",
                error=None,
            )
        outcome = self.harness.wait_completion(
            session, timeout=self._wait_timeout_sec(ctx.data_dir),
        )
        if outcome.ok and outcome.step_result:
            path = step_result_path(ctx.data_dir, ctx.task_id, ctx.step_id)
            return DispatchResult(
                ok=True,
                transport_used="file_bus",
                step_result_path=path,
            )

        err = outcome.error or "timeout waiting for step-result"
        self._audit_wait_timeout(
            ctx, msg_id, ack_received=outcome.ack_received, error=err,
        )
        return DispatchResult(
            ok=False,
            transport_used="file_bus",
            error=f"retryable:{err}",
        )

    def _mark_inbox_dispatched(self, inbox_path: str, msg_id: str) -> None:
        """spawn 成功后把该 inbox 消息标为 pushed（幂等标记，见上方 M2 注释）。"""
        try:
            with open(inbox_path, encoding="utf-8") as f:
                inbox = json.load(f)
            for m in reversed(inbox.get("messages", [])):
                if isinstance(m, dict) and m.get("id") == msg_id:
                    m["state"] = "pushed"
                    m["pushed_at"] = _now_iso()
                    m["pushed_via"] = "file_bus_dispatch"
                    break
            json_write(inbox_path, inbox)
        except (OSError, ValueError):
            pass  # 标记失败不阻断派发：最坏情况回到二推，agent 侧仍有 task 幂等

    def _dispatch_stub(self, ctx: DispatchContext, fixture_name: Optional[str]) -> DispatchResult:
        name = fixture_name or "path-d-agent-i-opencode.json"
        fixture = _load_stub_fixture(name)
        result = dict(fixture.get("on_complete_step_result") or {})
        if not result:
            return DispatchResult(ok=False, transport_used="file_bus", error="stub missing step_result")

        opencode = fixture.get("opencode_reply")
        if opencode:
            replies_dir = os.path.join(ctx.data_dir, "replies")
            os.makedirs(replies_dir, exist_ok=True)
            payload = dict(opencode)
            if payload.get("_file"):
                payload.pop("_file", None)
            json_write(os.path.join(replies_dir, f"{ctx.to_agent}.json"), payload)

        write_step_result_file(
            ctx.data_dir, ctx.task_id, ctx.step_id, result,
            agent=ctx.to_agent, role_type=ctx.role_type,
        )
        path = step_result_path(ctx.data_dir, ctx.task_id, ctx.step_id)
        return DispatchResult(
            ok=True,
            transport_used="file_bus",
            step_result_path=path,
            a2a_retries_exhausted=bool((fixture.get("transport_audit") or {}).get("a2a_retries_exhausted")),
        )
