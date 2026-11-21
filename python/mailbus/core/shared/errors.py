"""领域异常：api 层据此映射为统一错误包装。

领域层只表达「什么错了」，不关心 HTTP 状态码。
"""

from __future__ import annotations


class DomainError(Exception):
    """所有领域异常的基类。"""

    code = "domain_error"

    def __init__(self, message_zh: str) -> None:
        super().__init__(message_zh)
        self.message_zh = message_zh


class NotFoundError(DomainError):
    code = "not_found"


class AuthenticationError(DomainError):
    """未登录或凭证无效。"""

    code = "unauthorized"


class PermissionDeniedError(DomainError):
    code = "permission_denied"


class InvalidTransitionError(DomainError):
    code = "invalid_transition"


class InvalidStateError(DomainError):
    code = "invalid_state"


class IdempotencyConflictError(DomainError):
    code = "idempotency_conflict"


class CapacityError(DomainError):
    """服务容量已满（如长连接数超限），调用方稍后重试。"""

    code = "capacity_exceeded"


class RateLimitedError(DomainError):
    """调用过于频繁，需退避后重试。"""

    code = "rate_limited"
