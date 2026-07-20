"""Transport 层异常分类 — Router 重试决策。"""
from __future__ import annotations


class TransportError(Exception):
    """传输层基础异常。"""

    retryable: bool = False

    def __init__(self, message: str, *, code: str = ""):
        super().__init__(message)
        self.code = code


class RetryableTransportError(TransportError):
    retryable = True


class NonRetryableTransportError(TransportError):
    retryable = False


def classify_http_status(status: int) -> TransportError:
    msg = f"http_{status}"
    if status in (408, 429, 500, 502, 503, 504):
        return RetryableTransportError(msg, code=str(status))
    if 400 <= status < 500:
        return NonRetryableTransportError(msg, code=str(status))
    if status >= 500:
        return RetryableTransportError(msg, code=str(status))
    return NonRetryableTransportError(msg, code=str(status))
