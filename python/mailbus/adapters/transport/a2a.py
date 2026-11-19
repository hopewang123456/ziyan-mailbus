"""A2A 出站：POST 到员工登记的 endpoint。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable

from mailbus.adapters.transport.staging import event_document, recipient_of
from mailbus.core.shared.events import DeliveryResult, OutboxEvent

_TIMEOUT_SEC = 5.0


class A2aTransport:
    def __init__(self, resolve_endpoint: Callable[[str], str | None]) -> None:
        self._resolve = resolve_endpoint

    def send(self, event: OutboxEvent) -> DeliveryResult:
        recipient = recipient_of(event)
        endpoint = self._resolve(recipient)
        if not endpoint:
            return DeliveryResult(ok=False, error_code="endpoint_missing")
        body = json.dumps(event_document(event), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
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
