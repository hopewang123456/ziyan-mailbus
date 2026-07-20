"""推送阶段短生命周期上下文（供 model_flag / ollama 解析 data_dir）。"""
from __future__ import annotations

from typing import Any, Optional

_ctx: dict[str, Any] = {}


def set_push_context(*, data_dir: str = "", config: Optional[dict] = None) -> None:
    _ctx["data_dir"] = data_dir
    _ctx["config"] = config


def get_push_context() -> dict[str, Any]:
    return dict(_ctx)


def clear_push_context() -> None:
    _ctx.clear()
