"""mailbus 统一控制台输出 — 默认精简，MAILBUS_VERBOSE=1 显示调试信息。"""

from __future__ import annotations

import os
import sys

_VERBOSE = os.environ.get("MAILBUS_VERBOSE", "").strip().lower() in ("1", "true", "yes", "on")


def verbose() -> bool:
    return _VERBOSE


def info(msg: str) -> None:
    print(msg, flush=True)


def debug(msg: str) -> None:
    if _VERBOSE:
        print(msg, flush=True)


def warn(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
