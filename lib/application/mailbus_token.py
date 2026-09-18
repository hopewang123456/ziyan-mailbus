"""Mailbus Token use cases — AuthPort behavior."""
from __future__ import annotations

import os

from lib.composition import get_token_store
from lib.domain.types import AuthDecision, ClientContext

# 开启无 Token 写且未填 CIDR 时的安全默认（仅 loopback）
_DEFAULT_WRITE_FREE_CIDRS = ("127.0.0.1/32", "::1/128")


def _ip_in_network(addr: str, cidr: str) -> bool:
    """单 IP 或 CIDR 匹配（如 192.168.1.50 或 10.0.0.0/8）。"""
    import ipaddress

    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
        net = ipaddress.ip_network(cidr, strict=False)
        return ip in net
    except (ValueError, TypeError):
        return False


def _auth_block(config: dict | None) -> dict:
    cfg = config or {}
    auth = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
    return auth


def _write_free_cidrs(config: dict | None) -> list[str]:
    """合并 write_without_token_cidrs 与 legacy exempt_cidrs。"""
    cfg = config or {}
    auth = _auth_block(config)
    raw = (
        auth.get("write_without_token_cidrs")
        or auth.get("exempt_cidrs")
        or cfg.get("exempt_cidrs")
        or []
    )
    if isinstance(raw, str):
        raw = [raw]
    out = [str(x).strip() for x in raw if str(x).strip()]
    return out


def live_auth_config(data_dir: str, *, extra: dict | None = None) -> dict:
    """从 store/config.json 读 auth 段（设置页保存后无需重启即可生效）。"""
    from lib.infra.utils import json_read

    cfg = json_read(os.path.join(data_dir or "", "config.json"), {})
    auth = dict(cfg.get("auth") or {}) if isinstance(cfg.get("auth"), dict) else {}
    if extra:
        for k, v in extra.items():
            if v in (None, "", [], {}):
                continue
            if k not in auth or auth.get(k) in (None, "", [], {}):
                auth[k] = v
    return {"auth": auth}


def allow_write_without_token_enabled(config: dict | None) -> bool:
    auth = _auth_block(config)
    return bool(auth.get("allow_write_without_token"))


def _normalize_addr(addr: str) -> str:
    a = (addr or "").strip().lower()
    if a.startswith("::ffff:"):
        a = a.split("::ffff:", 1)[-1]
    return a


def ip_matches_write_free_cidrs(addr: str, config: dict | None) -> bool:
    """请求 IP 是否落在无 Token 写白名单（需先开启开关）。"""
    if not allow_write_without_token_enabled(config):
        return False
    a = _normalize_addr(addr)
    if a == "localhost":
        a = "127.0.0.1"
    cidrs = _write_free_cidrs(config) or list(_DEFAULT_WRITE_FREE_CIDRS)
    for cidr in cidrs:
        if cidr == a or _ip_in_network(a, cidr):
            return True
    return False


def _is_local(addr: str, extra_cidrs: list[str] | None = None) -> bool:
    """历史辅助：loopback / 显式 CIDR。写鉴权请用 ip_matches_write_free_cidrs。"""
    a = _normalize_addr(addr)
    if a in ("127.0.0.1", "::1", "localhost"):
        return True
    if extra_cidrs:
        for cidr in extra_cidrs:
            if _ip_in_network(a, cidr) or cidr == a:
                return True
    return False


def ensure_token(data_dir: str) -> str:
    return get_token_store().ensure_token(data_dir)


def resolve_token(data_dir: str, config: dict | None = None) -> str | None:
    return get_token_store().resolve_token(data_dir, config)


def authorize_write(data_dir: str, ctx: ClientContext, *, config: dict | None = None) -> AuthDecision:
    """写操作鉴权。

    默认（无 allow_write_without_token）：一律需要有效 Token（含本机）。
    开启后：仅 write_without_token_cidrs / exempt_cidrs 白名单内 IP 可无 Token 写
    （未填 CIDR 时默认仅 loopback）。
    """
    presented = _presented_token(ctx)
    expected = resolve_token(data_dir, config)

    if ip_matches_write_free_cidrs(ctx.remote_addr, config):
        if not presented:
            return AuthDecision.ALLOW
        if expected and presented == expected:
            return AuthDecision.ALLOW
        if expected and presented != expected:
            return AuthDecision.DENY
        return AuthDecision.ALLOW

    if not expected:
        return AuthDecision.DENY
    if presented and presented == expected:
        return AuthDecision.ALLOW
    return AuthDecision.DENY


def rotate_token(data_dir: str, ctx: ClientContext, *, config: dict | None = None) -> dict:
    """
    白名单无 Token 写网段：可无旧 token 轮换。
    其它：必须出示当前 token。
    """
    if ip_matches_write_free_cidrs(ctx.remote_addr, config):
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
