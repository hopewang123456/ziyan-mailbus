"""BridgedAgentPort — inbox write + file-bus ack poll (Wave 2).

Non-A2A agents: write via FileBusMessageTransport, optional ack poll with lifecycle_rules.
"""
from __future__ import annotations

import os
import time
from typing import Any, Mapping

from lib.adapters.results.ack import list_unacked
from lib.adapters.transport.bridge.lifecycle_rules import (
    ExitClass,
    classify_exit,
    should_retry,
    timeout_seconds,
)
from lib.adapters.transport.file_bus import FileBusMessageTransport
from lib.domain.error_codes import TRANSPORT_FILE_BUS
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.infra.utils import json_read


class CliBridgedAgent:
    """Implements BridgedAgentPort via inbox write + optional ack poll.

    Headers (OutboundMessage.headers):
      data_dir (required), wait=1 to poll ack, wait_timeout_sec, task_id, step_id
    """

    def __init__(self, data_dir: str = "", config: dict | None = None):
        self.data_dir = data_dir
        self.config = config or {}
        self._bus = FileBusMessageTransport()
        self._procs: dict[str, Any] = {}

    def send(self, message: OutboundMessage) -> TransportReceipt:
        h = dict(message.headers or {})
        data_dir = h.get("data_dir") or self.data_dir
        if not data_dir:
            return TransportReceipt(
                msg_id=message.msg_id,
                accepted=False,
                detail="missing data_dir",
                channel="cli_bridge",
                error_code=TRANSPORT_FILE_BUS,
            )
        # Ensure wait is off for the thin inbox write; we poll ack ourselves.
        thin = OutboundMessage(
            agent_id=message.agent_id,
            msg_id=message.msg_id,
            body_path=message.body_path,
            contract_path=message.contract_path,
            headers={**h, "data_dir": data_dir, "wait": "0"},
        )
        receipt = self._bus.send(thin)
        if not receipt.accepted:
            return TransportReceipt(
                msg_id=receipt.msg_id,
                accepted=False,
                detail=receipt.detail,
                channel="cli_bridge",
                error_code=receipt.error_code or TRANSPORT_FILE_BUS,
            )

        wait = (h.get("wait") or "").strip().lower() in ("1", "true", "yes", "on")
        if not wait:
            return TransportReceipt(
                msg_id=receipt.msg_id,
                accepted=True,
                detail="inbox_written",
                channel="cli_bridge",
            )

        agent_cfg = ((self.config.get("agents") or {}).get(message.agent_id) or {})
        timeout = int(h.get("wait_timeout_sec") or timeout_seconds(agent_cfg))
        ok = self._poll_ack(data_dir, message.agent_id, receipt.msg_id, timeout=timeout)
        if ok:
            return TransportReceipt(
                msg_id=receipt.msg_id,
                accepted=True,
                detail="inbox_written+ack",
                channel="cli_bridge",
            )
        return TransportReceipt(
            msg_id=receipt.msg_id,
            accepted=False,
            detail="timeout waiting for ack",
            channel="cli_bridge",
            error_code=TRANSPORT_FILE_BUS,
        )

    def cancel(
        self,
        *,
        agent_id: str,
        msg_id: str = "",
        task_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        proc = self._procs.pop(agent_id, None)
        if proc is not None and getattr(proc, "poll", lambda: 0)() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            return {
                "ok": True,
                "agent_id": agent_id,
                "msg_id": msg_id,
                "task_id": task_id,
                "reason": reason or "cancelled",
                "exit_class": ExitClass.FATAL.value,
            }
        return {
            "ok": False,
            "agent_id": agent_id,
            "msg_id": msg_id,
            "task_id": task_id,
            "error": "no_active_process",
            "reason": reason or "",
        }

    def status(
        self,
        *,
        agent_id: str,
        msg_id: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        data_dir = self.data_dir
        proc = self._procs.get(agent_id)
        running = bool(proc is not None and getattr(proc, "poll", lambda: 0)() is None)
        acked = False
        if data_dir and msg_id:
            remaining = list_unacked(data_dir, agent_id, [msg_id])
            acked = msg_id not in remaining
        exit_code = None if running or proc is None else getattr(proc, "returncode", None)
        exit_class = classify_exit(exit_code, timed_out=False) if exit_code is not None else (
            ExitClass.OK if acked else ExitClass.RETRYABLE
        )
        return {
            "agent_id": agent_id,
            "msg_id": msg_id,
            "task_id": task_id,
            "running": running,
            "acked": acked,
            "exit_code": exit_code,
            "exit_class": exit_class.value,
            "retryable": should_retry(exit_class, attempt=0),
        }

    def _poll_ack(self, data_dir: str, agent_id: str, msg_id: str, *, timeout: int) -> bool:
        deadline = time.monotonic() + max(1, timeout)
        while time.monotonic() < deadline:
            if msg_id and msg_id not in list_unacked(data_dir, agent_id, [msg_id]):
                return True
            # Also accept empty / missing msg_id via inbox ack file presence of any ack
            if not msg_id:
                ack_path = os.path.join(data_dir, "inbox", agent_id, "ack.json")
                data = json_read(ack_path, [])
                if isinstance(data, list) and data:
                    return True
            time.sleep(0.5)
        return False
