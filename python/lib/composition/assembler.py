"""L3 轻量装配器 — 声明式配置查表组装（D7/D8, P0c 2026-10-26）。

「选哪个实现」由 store config.json 的 ``composition`` 段声明；代码只提供
实现工厂（经 `lib.interfaces.assembler.register` 登记）。查表实例化，
不引入 IoC 容器（python 轻量自研路线，双栈差异化的 python 侧）。

约定：
- 配置缺省时用 ``default``（保持既有行为零迁移成本）；
- 实现工厂签名为 ``factory(ctx: dict)``，ctx 至少含 ``data_dir``；
- 未知实现名 fail-fast 抛 `AssemblyError`，不静默回退。
"""
from __future__ import annotations

from typing import Any

from lib.infra.utils import json_read
from lib.interfaces.assembler import resolve_factory


def load_composition_config(data_dir: str) -> dict:
    """store config.json 的 composition 段（无 config 时为空 dict）。"""
    import os

    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    comp = (cfg or {}).get("composition")
    return comp if isinstance(comp, dict) else {}


def assemble(
    slot: str,
    data_dir: str = "",
    *,
    default: str,
    config: dict | None = None,
    **ctx: Any,
) -> Any:
    """按 ``composition.<slot>`` 声明装配实现；缺省用 default。"""
    comp = config if config is not None else load_composition_config(data_dir)
    choice = str(comp.get(slot) or default).strip()
    factory = resolve_factory(slot, choice)
    full_ctx = {"data_dir": data_dir, **ctx}
    return factory(full_ctx)
