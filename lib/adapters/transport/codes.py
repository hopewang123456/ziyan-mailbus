"""Map legacy transport exceptions → domain errors + stable codes."""
from __future__ import annotations

from lib.domain.error_codes import (
    TRANSPORT_A2A,
    TRANSPORT_FATAL,
    TRANSPORT_HTTP,
    TRANSPORT_RETRYABLE,
    TRANSPORT_TIMEOUT,
)
from lib.domain.errors import Fatal, MailbusError, Retryable


def transport_exc_to_domain(exc: BaseException, *, channel: str = "") -> MailbusError:
    from lib.transport.errors import NonRetryableTransportError, RetryableTransportError, TransportError

    msg = str(exc)
    code = getattr(exc, "code", "") or ""
    if isinstance(exc, RetryableTransportError) or (
        isinstance(exc, TransportError) and getattr(exc, "retryable", False)
    ):
        ec = TRANSPORT_TIMEOUT if "timeout" in msg.lower() or code in ("408", "504") else TRANSPORT_RETRYABLE
        if channel == "a2a_standard" or channel == "http_a2a":
            ec = TRANSPORT_A2A if ec == TRANSPORT_RETRYABLE else ec
        if code.isdigit():
            ec = TRANSPORT_HTTP
        return Retryable(msg, code=ec)
    if isinstance(exc, NonRetryableTransportError):
        return Fatal(msg, code=code or TRANSPORT_FATAL)
    if isinstance(exc, TransportError):
        return Fatal(msg, code=code or TRANSPORT_FATAL)
    return Fatal(msg, code=TRANSPORT_FATAL)
