"""Mailbus Token use cases — AuthPort behavior."""
from __future__ import annotations

from lib.composition import get_token_store
from lib.domain.types import AuthDecision, ClientContext


def _is_local(addr: str) -> bool:
    """本机（loopback 或 Docker 网桥私有地址）视为本地免 token。"""
    a = (addr or "").strip().lower()
    if a.startswith("::ffff:"):
        a = a.split("::ffff:", 1)[-1]
    if a in ("127.0.0.1", "::1", "localhost"):
        return True
    # Docker / WSL2 网桥：mailbus 在容器内看到的客户端 IP 是宿主机侧网关
    # 常见的 Docker bridge: 172.17.0.0/16 · 172.18.0.0/16 · 172.19+ · 10.x
    try:
        parts = a.split(".")
        if len(parts) == 4:
            octets = [int(p) for p in parts]
            first_two = (octets[0] << 8) | octets[1]
            # 172.16.0.0/12 → 172.16.x.x – 172.31.x.x
            if first_two == 0xA00 or first_two == 0xA00 or 0xAC10 <= first_two <= 0xAC1F:
                return True
            # 10.0.0.0/8
            if octets[0] == 10:
                return True
            # 192.168.0.0/16
            if octets[0] == 192 and octets[1] == 168:
                return True
    except (ValueError, IndexError):
        pass
    return False


def ensure_token(data_dir: str) -> str:
    return get_token_store().ensure_token(data_dir)


def resolve_token(data_dir: str, config: dict | None = None) -> str | None:
    return get_token_store().resolve_token(data_dir, config)


def authorize_write(data_dir: str, ctx: ClientContext, *, config: dict | None = None) -> AuthDecision:
    """本机（含 Docker/WSL 网桥）写操作免 token；跨机需有效 token。"""
    if _is_local(ctx.remote_addr):
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
    if _is_local(ctx.remote_addr):
        token = get_token_store().rotate_token(data_dir)
        return {"ok": True, "token": token, "message": "rotated"}
    expected = resolve_token(data_dir, config)
    presented = _presented_token(ctx)
    if not expected or not presented or presented != expected:
        return {"ok": False, "error": "unauthorized", "error_code": "unauthorized"}
    token = get_token_store().rotate_token(data_dir)
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
