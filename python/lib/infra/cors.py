"""CORS helpers — 可配置 Origin 白名单，默认收紧。"""
from __future__ import annotations

from typing import Optional


def cors_allowed_origins(config: dict | None) -> list[str]:
    """auth.cors_origins 或顶层 cors_origins；空 = 仅同 Origin / 无反射 *。"""
    cfg = config or {}
    auth = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
    raw = auth.get("cors_origins") or cfg.get("cors_origins") or []
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    return [str(x).strip() for x in raw if str(x).strip()]


def pick_cors_origin(request_origin: str, config: dict | None) -> Optional[str]:
    """返回应写入 Access-Control-Allow-Origin 的值；不允许则 None。

    - 白名单含 ``*``：反射请求 Origin（若有），否则 ``*``
    - 白名单匹配：回显该 Origin
    - 白名单为空：不设置跨域（同站浏览器仍可用）
    """
    origin = (request_origin or "").strip()
    allowed = cors_allowed_origins(config)
    if not allowed:
        return None
    if "*" in allowed:
        return origin or "*"
    if origin and origin in allowed:
        return origin
    return None
