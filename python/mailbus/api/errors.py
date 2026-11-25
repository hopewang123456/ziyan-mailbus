"""统一错误包装：与既有 {error, error_code, message_zh} 形状保持一致。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mailbus.core.shared.errors import (
    AuthenticationError,
    CapacityError,
    DomainError,
    IdempotencyConflictError,
    InvalidStateError,
    InvalidTransitionError,
    NotFoundError,
    NotImplementedFeatureError,
    PermissionDeniedError,
    RateLimitedError,
    ResourceGoneError,
    UnprocessableError,
)

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    AuthenticationError: 401,
    NotFoundError: 404,
    PermissionDeniedError: 403,
    ResourceGoneError: 410,
    UnprocessableError: 422,
    InvalidTransitionError: 409,
    InvalidStateError: 409,
    IdempotencyConflictError: 409,
    CapacityError: 503,
    RateLimitedError: 429,
    NotImplementedFeatureError: 501,
}

# 领域错误码 → HTTP 状态：需要大写契约码的场景（api 不能 import 具体上下文）
_STATUS_BY_CODE: dict[str, int] = {
    "PAIR_NOT_FOUND": 404,
    "PAIR_CONFLICT": 409,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _envelope(
            exc.code,
            exc.message_zh,
            _status_of(exc),
            getattr(exc, "issues", None),
            getattr(exc, "revision", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope("validation_error", "请求参数不合法", 422)


def _status_of(exc: DomainError) -> int:
    """先按契约码，再按异常继承链匹配；子类不会退化成 400。"""
    if exc.code in _STATUS_BY_CODE:
        return _STATUS_BY_CODE[exc.code]
    for cls in type(exc).__mro__:
        status = _STATUS_BY_ERROR.get(cls)
        if status is not None:
            return status
    return 400


def _envelope(
    code: str,
    message_zh: str,
    status: int,
    issues: tuple[dict[str, object], ...] | list[dict[str, object]] | None = None,
    revision: int | None = None,
) -> JSONResponse:
    content: dict[str, object] = {
        "error": code,
        "error_code": code,
        "message_zh": message_zh,
    }
    if issues:
        content["errors"] = list(issues)
    if revision is not None:
        content["revision"] = revision
    return JSONResponse(status_code=status, content=content)
