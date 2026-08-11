"""Persist Mailbus API token in store/secrets.json (not git)."""
from __future__ import annotations

import os
import secrets
from typing import Any

from lib.infra.utils import file_lock, json_read, json_write

SECRETS_NAME = "secrets.json"
TOKEN_KEY = "mailbus_api_token"


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
