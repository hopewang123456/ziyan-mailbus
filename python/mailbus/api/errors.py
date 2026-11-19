"""统一错误包装：与既有 {error, error_code, message_zh} 形状保持一致。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mailbus.core.shared.errors import (
    AuthenticationError,
    DomainError,
    IdempotencyConflictError,
    InvalidStateError,
    InvalidTransitionError,
    NotFoundError,
    PermissionDeniedError,
)

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    AuthenticationError: 401,
    NotFoundError: 404,
    PermissionDeniedError: 403,
    InvalidTransitionError: 409,
    InvalidStateError: 409,
    IdempotencyConflictError: 409,
}

# 领域错误码 → HTTP 状态：需要大写契约码的场景（api 不能 import 具体上下文）
_STATUS_BY_CODE: dict[str, int] = {
    "PAIR_NOT_FOUND": 404,
    "PAIR_CONFLICT": 409,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = _STATUS_BY_CODE.get(exc.code) or _STATUS_BY_ERROR.get(type(exc), 400)
        return _envelope(exc.code, exc.message_zh, status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope("validation_error", "请求参数不合法", 422)


def _envelope(code: str, message_zh: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": code, "error_code": code, "message_zh": message_zh},
    )
