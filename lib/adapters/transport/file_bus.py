"""FileBus MessageTransportPort — write inbox message (send-only, no harness wait)."""
from __future__ import annotations

import json
import os
from typing import Mapping

from lib.domain.error_codes import TRANSPORT_FILE_BUS
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.utils import _now_iso, json_write


class FileBusMessageTransport:
    """Implements MessageTransportPort for local inbox delivery."""

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
        return TransportReceipt(
            msg_id=msg_id,
            accepted=True,
            detail="inbox_written",
            channel="file_bus",
        )
