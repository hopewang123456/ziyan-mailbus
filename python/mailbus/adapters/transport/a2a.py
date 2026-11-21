"""A2A 出站：POST 到员工登记的 endpoint。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from mailbus.adapters.transport.staging import event_document, recipient_of
from mailbus.core.shared.events import DeliveryResult, OutboxEvent

_TIMEOUT_SEC = 5.0
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _is_safe_endpoint(endpoint: str) -> bool:
    """只允许 http(s) 且必须有主机，杜绝 file/gopher 等方案被用于出站。"""
    try:
        parsed = urllib.parse.urlparse(endpoint)
    except (ValueError, TypeError):
        return False
    return parsed.scheme in _ALLOWED_SCHEMES and bool(parsed.netloc)


class A2aTransport:
    def __init__(
        self,
        resolve_endpoint: Callable[[str], str | None],
        bearer_token: str | None = None,
    ) -> None:
        self._resolve = resolve_endpoint
        self._token = bearer_token or os.getenv("A2A_BEARER_TOKEN") or None

    def send(self, event: OutboxEvent) -> DeliveryResult:
        recipient = recipient_of(event)
        endpoint = self._resolve(recipient)
        if not endpoint:
            return DeliveryResult(ok=False, error_code="endpoint_missing")
        if not _is_safe_endpoint(endpoint):
            return DeliveryResult(ok=False, error_code="a2a_invalid_endpoint")
        body = json.dumps(event_document(event), ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
                if 200 <= response.status < 300:
                    return DeliveryResult(ok=True, detail="a2a_delivered")
                return DeliveryResult(
                    ok=False, error_code="a2a_status", detail=str(response.status)
                )
        except (urllib.error.URLError, OSError) as exc:
            return DeliveryResult(ok=False, error_code="a2a_unreachable", detail=str(exc))
