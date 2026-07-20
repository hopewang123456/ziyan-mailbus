"""Production Harness — 薄包装 pusher（Phase 1 占位）。"""
from __future__ import annotations

import os
import time
import uuid

from ..pusher import _get_unacked_ids
from ..transport.step_result_io import read_step_result_file
from ..utils import json_read
from . import AgentHarness, HarnessOutcome, HarnessSession

_TERMINAL_STEP_STATUSES = frozenset({"done", "pass", "submitted", "ok"})


def _step_result_ready(data_dir: str, task_id: str, step_id: str) -> dict | None:
    result = read_step_result_file(data_dir, task_id, step_id)
    if not result:
        return None
    status = (result.get("status") or result.get("conclusion") or "").lower()
    if status in _TERMINAL_STEP_STATUSES:
        return result
    return None


def _msg_acked(data_dir: str, agent_id: str, msg_id: str) -> bool:
    if not msg_id:
        return False
    return msg_id not in _get_unacked_ids(data_dir, agent_id, [msg_id])


def _poll_side_effects(data_dir: str) -> None:
    """与 scanner/pusher 协作：归一化 OpenCode 投递并触发 scan 周期。"""
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = cfg.get("agents") or {}
    try:
        from ..delivery_normalizer import normalize_opencode_deliveries

        normalize_opencode_deliveries(data_dir, agents, config=cfg)
    except Exception:
        pass
    try:
        from ..scanner import scan_all

        scan_all(data_dir, agents)
    except Exception:
        pass


class ProductionHarness(AgentHarness):
    """真实 CLI 推送由 scanner/pusher 完成；wait 轮询 ack / step-result。"""

    def spawn(self, agent_id: str, payload: dict) -> HarnessSession:
        task_id = str(payload.get("task_id") or "")
        step_id = str(payload.get("step_id") or "")
        msg_id = str(payload.get("msg_id") or "")
        if not msg_id and task_id and step_id:
            msg_id = f"msg-{task_id}-{step_id}"
        return HarnessSession(
            session_id=f"prod-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            framework=str(payload.get("framework") or ""),
            transport_channel=str(payload.get("transport_channel") or "file_bus"),
            data_dir=str(payload.get("data_dir") or ""),
            task_id=task_id,
            step_id=step_id,
            msg_id=msg_id,
        )

    def wait_completion(self, session: HarnessSession, timeout: int = 300) -> HarnessOutcome:
        data_dir = session.data_dir
        task_id = session.task_id
        step_id = session.step_id
        if not data_dir or not task_id or not step_id:
            return HarnessOutcome(
                ok=False,
                error="production wait requires data_dir, task_id, step_id in spawn payload",
            )

        deadline = time.time() + timeout
        ack_received = False
        round_n = 0
        while time.time() < deadline:
            round_n += 1
            if session.msg_id and not ack_received:
                ack_received = _msg_acked(data_dir, session.agent_id, session.msg_id)

            result = _step_result_ready(data_dir, task_id, step_id)
            if result:
                return HarnessOutcome(
                    ok=True,
                    ack_received=ack_received or not session.msg_id,
                    step_result=result,
                )

            if round_n % 2 == 0:
                _poll_side_effects(data_dir)

            time.sleep(1)

        return HarnessOutcome(
            ok=False,
            ack_received=ack_received,
            error="timeout waiting for step-result",
        )
