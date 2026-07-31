"""FileBus MessageTransportPort — inbox write; optional Harness wait (W7c)."""
from __future__ import annotations

import json
import os
from typing import Mapping

from lib.domain.error_codes import TRANSPORT_FILE_BUS
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.utils import _now_iso, json_read, json_write


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


class FileBusMessageTransport:
    """Implements MessageTransportPort for local inbox delivery.

    Headers:
      data_dir (required), intent/content, task_id, step_id, from_agent, ...
      wait=1|true — after inbox write, spawn harness + wait_completion (厚路径)
      allow_no_spawn=1 — pass through to ProductionHarness (tests / no CLI)
      wait_timeout_sec — override ack/step-result wait timeout
    """

    def send(self, message: OutboundMessage) -> TransportReceipt:
        h = dict(message.headers or {})
        data_dir = h.get("data_dir") or ""
        if not data_dir:
            return TransportReceipt(
                msg_id=message.msg_id,
                accepted=False,
                detail="missing data_dir",
                channel="file_bus",
                error_code=TRANSPORT_FILE_BUS,
            )
        agent = message.agent_id
        inbox_dir = os.path.join(data_dir, "inbox", agent)
        os.makedirs(inbox_dir, exist_ok=True)
        inbox_path = os.path.join(inbox_dir, "inbox.json")
        inbox = {"agent": agent, "messages": []}
        if os.path.isfile(inbox_path):
            try:
                with open(inbox_path, encoding="utf-8") as f:
                    inbox = json.load(f)
            except Exception:
                pass
        content = h.get("intent") or h.get("content") or ""
        if not content and message.body_path and os.path.isfile(message.body_path):
            try:
                with open(message.body_path, encoding="utf-8") as f:
                    content = f.read()
            except Exception as exc:
                return TransportReceipt(
                    msg_id=message.msg_id,
                    accepted=False,
                    detail=str(exc),
                    channel="file_bus",
                    error_code=TRANSPORT_FILE_BUS,
                )
        msg_id = message.msg_id or f"msg-{h.get('task_id', '')}-{h.get('step_id', '')}"
        inbox.setdefault("messages", []).append({
            "id": msg_id,
            "from": h.get("from_agent") or "mailbus",
            "to": agent,
            "type": h.get("msg_type") or "task",
            "state": "pending",
            "task_id": h.get("task_id") or "",
            "step_id": h.get("step_id") or "",
            "content": content,
            "created_at": _now_iso(),
            "contract_path": message.contract_path or "",
        })
        json_write(inbox_path, inbox)

        if not _truthy(h.get("wait")):
            return TransportReceipt(
                msg_id=msg_id,
                accepted=True,
                detail="inbox_written",
                channel="file_bus",
            )

        return self._wait_harness(message, h, data_dir, agent, msg_id)

    def _wait_harness(
        self,
        message: OutboundMessage,
        h: Mapping[str, str],
        data_dir: str,
        agent: str,
        msg_id: str,
    ) -> TransportReceipt:
        from lib.harness import get_harness

        cfg = json_read(os.path.join(data_dir, "config.json"), {})
        harness = get_harness(cfg)
        timeout = int(
            h.get("wait_timeout_sec")
            or ((cfg.get("harness") or {}).get("file_bus") or {}).get("ack_timeout_sec")
            or cfg.get("ack_timeout")
            or 300
        )
        agents = cfg.get("agents") or {}
        agent_cfg = agents.get(agent) or {}
        session = harness.spawn(
            agent,
            {
                "data_dir": data_dir,
                "task_id": h.get("task_id") or "",
                "step_id": h.get("step_id") or "",
                "msg_id": msg_id,
                "prompt": h.get("intent") or h.get("content") or "",
                "framework": agent_cfg.get("type") or "",
                "transport_channel": "file_bus",
                "allow_no_spawn": _truthy(h.get("allow_no_spawn")),
                "contract_path": message.contract_path or "",
            },
        )
        outcome = harness.wait_completion(session, timeout=timeout)
        if outcome.ok:
            detail = "inbox_written+wait_ok"
            if outcome.step_result:
                detail = "inbox_written+step_result"
            return TransportReceipt(
                msg_id=msg_id,
                accepted=True,
                detail=detail,
                channel="file_bus",
            )
        err = outcome.error or "timeout waiting for step-result"
        return TransportReceipt(
            msg_id=msg_id,
            accepted=False,
            detail=err,
            channel="file_bus",
            error_code=TRANSPORT_FILE_BUS,
        )
