"""Transport 层异常分类 — Router 重试决策；对齐 domain 错误码（Wave3）。"""
from __future__ import annotations

from lib.domain.error_codes import TRANSPORT_FATAL, TRANSPORT_HTTP, TRANSPORT_RETRYABLE
from lib.domain.errors import Fatal, Retryable


class TransportError(Exception):
    """传输层基础异常。"""

    retryable: bool = False

    def __init__(self, message: str, *, code: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_domain(self) -> Retryable | Fatal:
        if self.retryable:
            return Retryable(self.message, code=self.code or TRANSPORT_RETRYABLE)
        return Fatal(self.message, code=self.code or TRANSPORT_FATAL)


class RetryableTransportError(TransportError):
    retryable = True


class NonRetryableTransportError(TransportError):
    retryable = False


def classify_http_status(status: int) -> TransportError:
    msg = f"http_{status}"
    if status in (408, 429, 500, 502, 503, 504):
        return RetryableTransportError(msg, code=str(status) or TRANSPORT_HTTP)
    if 400 <= status < 500:
        return NonRetryableTransportError(msg, code=str(status) or TRANSPORT_FATAL)
    if status >= 500:
        return RetryableTransportError(msg, code=str(status) or TRANSPORT_HTTP)
    return NonRetryableTransportError(msg, code=str(status) or TRANSPORT_FATAL)
