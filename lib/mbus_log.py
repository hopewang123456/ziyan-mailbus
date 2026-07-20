"""Mailbus 结构化日志 — stderr + 可选 data_dir/logs/mbus.log。"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
_DEFAULT_LEVEL = "info"
_env_level = (os.environ.get("MAILBUS_LOG_LEVEL") or _DEFAULT_LEVEL).lower()


def _enabled(level: str) -> bool:
    return _LEVELS.get(level, 20) >= _LEVELS.get(_env_level, 20)


def _format(level: str, msg: str, *args: Any) -> str:
    text = msg % args if args else msg
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts} [{level.upper()}] {text}"


def _emit(level: str, msg: str, *args: Any) -> None:
    if not _enabled(level):
        return
    line = _format(level, msg, *args)
    print(line, file=sys.stderr, flush=True)
    data_dir = os.environ.get("MAILBUS_DATA_DIR") or os.environ.get("MAILBUS_STORE")
    if not data_dir:
        return
    try:
        log_dir = os.path.join(data_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "mbus.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def debug(msg: str, *args: Any) -> None:
    _emit("debug", msg, *args)


def info(msg: str, *args: Any) -> None:
    _emit("info", msg, *args)


def warn(msg: str, *args: Any) -> None:
    _emit("warn", msg, *args)


def error(msg: str, *args: Any) -> None:
    _emit("error", msg, *args)
