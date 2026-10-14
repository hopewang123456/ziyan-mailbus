"""Compat shim — 实际实现已下沉到 `lib.infra.push_context`。"""
from lib.infra.push_context import (  # noqa: F401
    set_push_context,
    get_push_context,
    clear_push_context,
)

__all__ = ["set_push_context", "get_push_context", "clear_push_context"]