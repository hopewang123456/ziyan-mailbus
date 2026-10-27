"""L3 装配器协议 — 实现注册表（D7/D8, P0c 2026-10-26）。

放 interfaces 层的原因：实现方是 adapters（adapters→interfaces 合法），
查表方是 composition 组合根（composition→interfaces 合法）；放 composition
会造成 adapters→composition 反向依赖。

用法（实现侧，adapters 内）::

    from lib.interfaces.assembler import register

    @register("audit", "file")
    def _build_file_audit(ctx):
        return FileAuditAdapter(ctx["data_dir"])

用法（装配侧，composition 内）::

    from lib.composition.assembler import assemble
    audit = assemble("audit", data_dir, default="file")

选择声明在 store config.json 的 ``composition`` 段::

    {"composition": {"audit": "file", "notifier": "file"}}
"""
from __future__ import annotations

from typing import Any, Callable

# "slot" -> {"impl_name": factory(ctx) -> 实例}
REGISTRY: dict[str, dict[str, Callable[[dict], Any]]] = {}


class AssemblyError(RuntimeError):
    """装配失败：未知实现名 / 注册缺失。fail-fast，不静默回退。"""


def register(slot: str, name: str) -> Callable[[Callable], Callable]:
    """把实现工厂登记到 ``<slot>.<name>``。同名重复登记视为 bug，直接抛错。"""

    def deco(factory: Callable[[dict], Any]) -> Callable[[dict], Any]:
        slot_map = REGISTRY.setdefault(slot, {})
        if name in slot_map:
            raise AssemblyError(f"adapter slot '{slot}.{name}' already registered")
        slot_map[name] = factory
        return factory

    return deco


def registered_impls(slot: str) -> tuple[str, ...]:
    """某 slot 的可用实现名（诊断/自检用）。"""
    return tuple(sorted(REGISTRY.get(slot, {})))


def resolve_factory(slot: str, choice: str) -> Callable[[dict], Any]:
    slot_map = REGISTRY.get(slot, {})
    factory = slot_map.get(choice)
    if factory is None:
        available = ", ".join(sorted(slot_map)) or "(none registered)"
        raise AssemblyError(
            f"composition.{slot}='{choice}' 未知；可用实现: {available}"
        )
    return factory
