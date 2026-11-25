"""告警通知适配器：webhook / 邮件 / 站内，单次投递 5 秒超时。"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage
from typing import Any

_TIMEOUT_SEC = 5.0


class AlertNotifier:
    """只做单次投递；重试与失败审计由应用层负责。"""

    def send(self, channel: str, target: str | None, payload: dict[str, Any]) -> None:
        if channel == "inapp":
            # 站内通知即 /api/alerts 中的告警本身，无需额外投递。
            return
        if channel == "webhook":
            self._webhook(target, payload)
            return
        if channel == "email":
            self._email(target, payload)
            return
        raise ValueError(f"不支持的通知渠道：{channel}")

    @staticmethod
    def _webhook(target: str | None, payload: dict[str, Any]) -> None:
        if not target:
            raise ValueError("webhook 渠道需要 target URL")
        request = urllib.request.Request(
            target,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            if response.status >= 400:
                raise RuntimeError(f"webhook 返回 {response.status}")

    @staticmethod
    def _email(target: str | None, payload: dict[str, Any]) -> None:
        host = os.environ.get("MAILBUS_SMTP_HOST", "").strip()
        if not host:
            raise RuntimeError("邮件通道未配置 MAILBUS_SMTP_HOST")
        if not target:
            raise ValueError("email 渠道需要接收人地址")
        port = int(os.environ.get("MAILBUS_SMTP_PORT", "25"))
        sender = os.environ.get("MAILBUS_SMTP_FROM", "mailbus@localhost")
        message = EmailMessage()
        message["From"] = sender
        message["To"] = target
        message["Subject"] = f"[mailbus] {payload.get('type', 'alert')}"
        message.set_content(json.dumps(payload, ensure_ascii=False, indent=2))
        with smtplib.SMTP(host, port, timeout=_TIMEOUT_SEC) as smtp:
            smtp.send_message(message)
