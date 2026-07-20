"""Webhook 推送 — 将 inbox 消息 POST 到 agent 配置的 webhook_url。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any

from .models import MsgStatus
from .scanner import mark_as_pushed, update_message_status
from .utils import _now_iso


def _sign_body(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _post_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    webhook_secret: str = "",
    timeout: float = 30.0,
) -> int:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if webhook_secret:
        headers["X-Mailbus-Signature"] = _sign_body(webhook_secret, body)
    req = urllib.request.Request(webhook_url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def push_via_webhook(
    *,
    data_dir: str,
    agent_name: str,
    messages: list[dict[str, Any]],
    webhook_url: str,
    max_retries: int = 3,
    webhook_secret: str = "",
    auto_ack: bool = False,
) -> list[str]:
    """POST 消息到 webhook；返回最终仍失败的 msg id 列表。"""
    if not messages:
        return []

    msg_ids = [m.get("id") for m in messages if m.get("id")]
    payload = {
        "action": "push",
        "agent": agent_name,
        "messages": messages,
        "timestamp": _now_iso(),
    }
    if auto_ack:
        payload["auto_ack"] = True

    backoff = (1.0, 2.0, 4.0)
    attempts = max(1, int(max_retries) + 1)
    ok = False
    for attempt in range(attempts):
        status = _post_webhook(webhook_url, payload, webhook_secret=webhook_secret)
        if 200 <= status < 300:
            ok = True
            break
        if attempt < attempts - 1:
            time.sleep(backoff[min(attempt, len(backoff) - 1)])

    if ok:
        mark_as_pushed(data_dir, agent_name, msg_ids)
        if auto_ack:
            for mid in msg_ids:
                update_message_status(data_dir, agent_name, mid, MsgStatus.ACKNOWLEDGED)
        return []

    return msg_ids
