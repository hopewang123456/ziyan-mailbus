"""Webhook HTTP 推送（HMAC 签名 + POST）— infra 层 I/O helper。

原位置 `lib/application/push/webhook_pusher._post_webhook` / `_sign_body`
（2026-09 治理下沉）。这两个函数是纯 stdlib + HTTP + HMAC，无 application 子树依赖，
放在 infra 是合理归宿；`push_via_webhook` 仍保留在 application（含业务编排 mark_as_pushed
等），并通过 compat shim 继续可用。

新代码请直接 import `lib.infra.http_webhook`。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from typing import Any


def _sign_body(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    webhook_secret: str = "",
    timeout: float = 30.0,
) -> int:
    """POST JSON payload 到 webhook_url，HMAC 签名头（可选）。

    返回 HTTP status code（成功 200-299，HTTPError 返回其 code）。
    公开 API（无下划线）；旧别名 `_post_webhook` 保留 compat。
    """
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


# 旧名（lib.application.push.webhook_pusher._post_webhook 用过）
_post_webhook = post_webhook


__all__ = ["post_webhook", "_sign_body", "_post_webhook"]