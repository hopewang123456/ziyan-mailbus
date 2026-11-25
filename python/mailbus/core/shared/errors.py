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


class VersionConflictError(InvalidStateError):
    """配置版本 CAS 失败（HTTP 409）。"""

    code = "version_conflict"


class StaleRunError(InvalidStateError):
    """A2A/认领结果引用了过期或不存在的 run attempt（HTTP 409）。"""

    code = "stale_run"


class ResourceGoneError(DomainError):
    """资源已撤销、已过期或已消费（HTTP 410）。"""

    code = "resource_gone"


class UnprocessableError(DomainError):
    """请求语义不成立，如 Agent 员工缺少岗位（HTTP 422）。"""

    code = "unprocessable"


class IdempotencyConflictError(DomainError):
    code = "idempotency_conflict"


class CapacityError(DomainError):
    """服务容量已满（如长连接数超限），调用方稍后重试。"""

    code = "capacity_exceeded"


class RateLimitedError(DomainError):
    """调用过于频繁，需退避后重试。"""

    code = "rate_limited"


class NotImplementedFeatureError(DomainError):
    """契约已冻结、实现尚未落地的端点（B1.5 契约桩）。"""

    code = "NOT_IMPLEMENTED"
