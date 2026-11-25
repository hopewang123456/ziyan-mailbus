"""鉴权依赖：Bearer token → Actor；写路由的权限声明标记。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import Request

from mailbus.application.identity.dto import Actor
from mailbus.core.shared.errors import AuthenticationError, NotImplementedFeatureError
from mailbus.core.shared.values import Capability

# 写路由的两种非能力标记：公开入口 / 仅需登录（由用例内部自行约束）
PUBLIC = "public"
SELF = "self"

_F = TypeVar("_F", bound=Callable[..., Any])


def declares(marker: Capability | str) -> Callable[[_F], _F]:
    """给路由函数打上所需能力标记（守卫 G8 据此校验）。"""
    value = marker.value if isinstance(marker, Capability) else marker

    def decorate(func: _F) -> _F:
        func.__mailbus_capability__ = value  # type: ignore[attr-defined]
        return func

    return decorate


def not_implemented() -> None:
    """B1.5 契约桩：契约已冻结，实现留给 B2–B7。"""
    raise NotImplementedFeatureError("该契约端点尚未实现")


def get_actor(request: Request) -> Actor:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("缺少 Bearer 凭证")
    return request.app.state.container.identity.sessions.resolve(token.strip())


def get_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("缺少 Bearer 凭证")
    return token.strip()
