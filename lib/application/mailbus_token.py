"""Mailbus Token use cases — AuthPort behavior."""
from __future__ import annotations

from lib.composition import get_token_store
from lib.domain.types import AuthDecision, ClientContext


def _ip_in_network(addr: str, cidr: str) -> bool:
    """单 IP 或 CIDR 匹配（如 192.168.1.50 或 10.0.0.0/8）。"""
    import ipaddress

    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
        net = ipaddress.ip_network(cidr, strict=False)
        return ip in net
    except (ValueError, TypeError):
        return False


def _exempt_cidrs(config: dict | None) -> list[str]:
    """从 config 读豁免 IP 白名单：config["auth"]["exempt_cidrs"] 或 config["exempt_cidrs"]。"""
    cfg = config or {}
    auth = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
    raw = auth.get("exempt_cidrs") or cfg.get("exempt_cidrs") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(x).strip() for x in raw if str(x).strip()]


def _is_local(addr: str, extra_cidrs: list[str] | None = None) -> bool:
    """本机视为免 token：loopback 或 Docker bridge 私有地址，或用户豁免白名单。

    只认 loopback 与 Docker/WSL2 标准网桥 172.16.0.0/12。
    （10.x / 192.168.x 不视为本机——内网主机同样需要 token，避免安全边界过宽。
    如需放行可经 exempt_cidrs 白名单显式配置。）
    """
    a = (addr or "").strip().lower()
    if a.startswith("::ffff:"):
        a = a.split("::ffff:", 1)[-1]
    if a in ("127.0.0.1", "::1", "localhost"):
        return True
    # 用户豁免白名单（优先级高，可覆盖 10.x/192.168 等自定义网段）
    if extra_cidrs:
        for cidr in extra_cidrs:
            if _ip_in_network(a, cidr):
                return True
    # Docker / WSL2 网桥：mailbus 在容器内看到的客户端 IP 是宿主机侧网关
    # 常见 Docker bridge: 172.17.0.0/16 · 172.18.0.0/16 · 172.19+（均在 172.16/12 内）
    try:
        parts = a.split(".")
        if len(parts) == 4:
            octets = [int(p) for p in parts]
            first_two = (octets[0] << 8) | octets[1]
            # 172.16.0.0/12 → 172.16.x.x – 172.31.x.x
            if 0xAC10 <= first_two <= 0xAC1F:
                return True
    except (ValueError, IndexError):
        pass
    return False


def ensure_token(data_dir: str) -> str:
    return get_token_store().ensure_token(data_dir)


def resolve_token(data_dir: str, config: dict | None = None) -> str | None:
    return get_token_store().resolve_token(data_dir, config)


def authorize_write(data_dir: str, ctx: ClientContext, *, config: dict | None = None) -> AuthDecision:
    """本机（含 Docker/WSL 网桥 + 用户豁免白名单）写操作免 token；跨机需有效 token。"""
    extra = _exempt_cidrs(config)
    if _is_local(ctx.remote_addr, extra_cidrs=extra):
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
    if _is_local(ctx.remote_addr, extra_cidrs=_exempt_cidrs(config)):
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
