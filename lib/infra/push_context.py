"""推送阶段短生命周期上下文（供 model_flag / ollama 解析 data_dir）。

原位置 `lib/application/push/push_context.py`（2026-09 治理下沉到 infra）。
模块级全局 dict 的 read/write/clear，无 application 子树依赖，infra 层合理。
adapter 也需要读 → 之前 adapter→application 跨层违规修掉。
application 保留 compat shim。
"""
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


__all__ = ["set_push_context", "get_push_context", "clear_push_context"]