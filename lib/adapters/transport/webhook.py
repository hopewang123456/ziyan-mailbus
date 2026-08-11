"""Webhook MessageTransportPort — POST single outbound message."""
from __future__ import annotations

import json
import os

from lib.domain.error_codes import TRANSPORT_HTTP, TRANSPORT_WEBHOOK
from lib.domain.types import OutboundMessage, TransportReceipt
from lib.infra.utils import _now_iso, json_read


class WebhookMessageTransport:
    def __init__(self, data_dir: str = "", config: dict | None = None):
        self.data_dir = data_dir
        self.config = config

    def send(self, message: OutboundMessage) -> TransportReceipt:
        h = dict(message.headers or {})
        data_dir = h.get("data_dir") or self.data_dir
        cfg = self.config or (
            json_read(os.path.join(data_dir, "config.json"), {}) if data_dir else {}
        )
        agent_cfg = (cfg.get("agents") or {}).get(message.agent_id) or {}
        url = h.get("webhook_url") or agent_cfg.get("webhook_url") or ""
        if not url:
            return TransportReceipt(
                msg_id=message.msg_id,
                accepted=False,
                detail="webhook_url missing",
                channel="webhook",
                error_code=TRANSPORT_WEBHOOK,
            )
        content = h.get("intent") or h.get("content") or ""
        if message.body_path and os.path.isfile(message.body_path):
            try:
                with open(message.body_path, encoding="utf-8") as f:
                    raw = f.read()
                try:
                    body_obj = json.loads(raw)
                    content = body_obj if isinstance(body_obj, (dict, list)) else raw
                except json.JSONDecodeError:
                    content = raw
            except Exception as exc:
                return TransportReceipt(
                    msg_id=message.msg_id,
                    accepted=False,
                    detail=str(exc),
                    channel="webhook",
                    error_code=TRANSPORT_WEBHOOK,
                )
        msg = {
            "id": message.msg_id,
            "from": h.get("from_agent") or "mailbus",
            "to": message.agent_id,
            "type": h.get("msg_type") or "task",
            "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
            "task_id": h.get("task_id") or "",
            "step_id": h.get("step_id") or "",
            "created_at": _now_iso(),
        }
        secret = h.get("webhook_secret") or agent_cfg.get("webhook_secret") or ""
        try:
            from lib.application.push.webhook_pusher import _post_webhook

            status = _post_webhook(
                url,
                {"action": "push", "agent": message.agent_id, "messages": [msg], "timestamp": _now_iso()},
                webhook_secret=secret,
            )
            ok = 200 <= status < 300
            return TransportReceipt(
                msg_id=message.msg_id,
                accepted=ok,
                detail=f"http_{status}",
                channel="webhook",
                error_code="" if ok else (TRANSPORT_HTTP if status else TRANSPORT_WEBHOOK),
            )
        except Exception as exc:
            return TransportReceipt(
                msg_id=message.msg_id,
                accepted=False,
                detail=str(exc),
                channel="webhook",
                error_code=TRANSPORT_WEBHOOK,
            )
