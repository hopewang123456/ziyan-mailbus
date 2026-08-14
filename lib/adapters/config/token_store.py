"""Persist Mailbus API token in store/secrets.json (not git)."""
from __future__ import annotations

import os
import secrets
from typing import Any

from lib.infra.utils import file_lock, json_read, json_write

SECRETS_NAME = "secrets.json"
TOKEN_KEY = "mailbus_api_token"
BROWSER_AUTH_KEY = "browser_auth"


def secrets_path(data_dir: str) -> str:
    return os.path.join(data_dir, SECRETS_NAME)


def read_secrets(data_dir: str) -> dict[str, Any]:
    return json_read(secrets_path(data_dir), {})


def write_secrets(data_dir: str, data: dict[str, Any]) -> None:
    path = secrets_path(data_dir)
    with file_lock(path=path):
        json_write(path, data)


def resolve_token(data_dir: str, config: dict | None = None) -> str | None:
    """Priority: env > secrets.json (mailbus_api_token)."""
    _ = config
    env = (os.environ.get("MAILBUS_API_TOKEN") or "").strip()
    if env:
        return env
    sec = read_secrets(data_dir)
    tok = (sec.get(TOKEN_KEY) or "").strip()
    return tok or None


def ensure_token(data_dir: str) -> str:
    existing = resolve_token(data_dir)
    if existing:
        return existing
    path = secrets_path(data_dir)
    with file_lock(path=path):
        data = json_read(path, {})
        if (data.get(TOKEN_KEY) or "").strip():
            return str(data[TOKEN_KEY]).strip()
        token = secrets.token_urlsafe(32)
        data[TOKEN_KEY] = token
        json_write(path, data)
        return token


def rotate_token(data_dir: str) -> str:
    path = secrets_path(data_dir)
    with file_lock(path=path):
        data = json_read(path, {})
        token = secrets.token_urlsafe(32)
        data[TOKEN_KEY] = token
        json_write(path, data)
        return token


def browser_credentials(data_dir: str, agent_id: str) -> dict[str, str]:
    """读取 secrets.json 下 browser_auth.<agent_id> 的凭据（user/pass 或 token）。"""
    sec = read_secrets(data_dir)
    block = (sec.get(BROWSER_AUTH_KEY) or {}).get(agent_id)
    return dict(block) if isinstance(block, dict) else {}


def ensure_browser_credentials(
    data_dir: str,
    agent_id: str,
    *,
    mode: str = "basic",
    token: str | None = None,
) -> dict[str, str]:
    """生成/读取 browser_auth.<agent_id> 强随机凭据（跨重启不变）。

    - mode=basic → user + password（ttyd -c / Hermes Basic Auth）
    - mode=token → token（OpenClaw gateway / Hermes session token）

    已存在的字段保留，缺失的补齐；显式 ``token`` 参数覆盖。
    """
    path = secrets_path(data_dir)
    with file_lock(path=path):
        data = json_read(path, {})
        ba = data.setdefault(BROWSER_AUTH_KEY, {})
        cur = dict(ba.get(agent_id) or {})
        if mode == "token":
            if token:
                cur["token"] = token
            elif not (cur.get("token") or "").strip():
                cur["token"] = secrets.token_urlsafe(24)
        else:
            if not (cur.get("user") or "").strip():
                cur["user"] = f"mb_{agent_id}"
            if not (cur.get("password") or "").strip():
                cur["password"] = secrets.token_urlsafe(18)
        ba[agent_id] = cur
        json_write(path, data)
        return dict(cur)

