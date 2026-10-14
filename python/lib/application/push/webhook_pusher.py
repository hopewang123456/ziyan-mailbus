"""Webhook 推送 — 将 inbox 消息 POST 到 agent 配置的 webhook_url。

HTTP POST + HMAC 签名的底层 I/O 已下沉到 `lib.infra.http_webhook`；本模块只保留
业务编排（push_via_webhook 处理 retry / mark_as_pushed / update_message_status）。
"""
from __future__ import annotations

import time
from typing import Any

from lib.domain.models import MsgStatus
from lib.application.scan import mark_as_pushed, update_message_status
from lib.infra.http_webhook import post_webhook as _post_webhook  # compat alias
from lib.infra.utils import _now_iso


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
