from __future__ import annotations

from typing import Protocol, runtime_checkable

from lib.domain.types import AuthDecision, ClientContext


@runtime_checkable
class AuthPort(Protocol):
    def ensure_token(self) -> str: ...

    def rotate_token(self, ctx: ClientContext) -> str: ...

    def authorize_write(self, ctx: ClientContext) -> AuthDecision: ...

    def resolve_token(self) -> str | None: ...
