"""Mailbus Token use cases — AuthPort behavior."""
from __future__ import annotations

from lib.adapters.config import token_store
from lib.domain.types import AuthDecision, ClientContext


def _is_loopback(addr: str) -> bool:
    a = (addr or "").strip().lower()
    if a.startswith("::ffff:"):
        a = a.split("::ffff:", 1)[-1]
    return a in ("127.0.0.1", "::1", "localhost")


def ensure_token(data_dir: str) -> str:
    return token_store.ensure_token(data_dir)


def resolve_token(data_dir: str, config: dict | None = None) -> str | None:
    return token_store.resolve_token(data_dir, config)


def authorize_write(data_dir: str, ctx: ClientContext, *, config: dict | None = None) -> AuthDecision:
    """Localhost writes allowed without token; remote requires valid token."""
    if _is_loopback(ctx.remote_addr):
        # If client sent a token, still validate when present
        presented = _presented_token(ctx)
        if not presented:
            return AuthDecision.ALLOW
        expected = resolve_token(data_dir, config)
        if expected and presented == expected:
            return AuthDecision.ALLOW
        if expected and presented != expected:
            return AuthDecision.DENY
        return AuthDecision.ALLOW

    expected = resolve_token(data_dir, config)
    if not expected:
        # Cross-host write without any configured token → deny (force generate locally first)
        return AuthDecision.DENY
    presented = _presented_token(ctx)
    if presented and presented == expected:
        return AuthDecision.ALLOW
    return AuthDecision.DENY


def rotate_token(data_dir: str, ctx: ClientContext, *, config: dict | None = None) -> dict:
    """
    Localhost: may rotate without old token.
    Remote: must present current token; old value invalidated on success.
    """
    if _is_loopback(ctx.remote_addr):
        token = token_store.rotate_token(data_dir)
        return {"ok": True, "token": token, "message": "rotated"}
    expected = resolve_token(data_dir, config)
    presented = _presented_token(ctx)
    if not expected or not presented or presented != expected:
        return {"ok": False, "error": "unauthorized", "error_code": "unauthorized"}
    token = token_store.rotate_token(data_dir)
    return {"ok": True, "token": token, "message": "rotated"}


def _presented_token(ctx: ClientContext) -> str:
    auth = (ctx.authorization or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (ctx.api_key_header or "").strip()


def client_context_from_handler(handler) -> ClientContext:
    addr = ""
    try:
        addr = handler.client_address[0]
    except Exception:
        addr = ""
    return ClientContext(
        remote_addr=str(addr),
        authorization=str(handler.headers.get("Authorization", "") or ""),
        api_key_header=str(handler.headers.get("X-API-Key", "") or ""),
    )
