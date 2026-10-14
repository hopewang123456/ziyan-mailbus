"""Minimal integration plugin registry (Wave4 · S4).

Builtins register on import; third-party can call ``register_integration``.
No hot-reload — load-time only.
"""
from __future__ import annotations

from typing import Any, Callable

Factory = Callable[..., Any]

_REGISTRY: dict[str, Factory] = {}
_META: dict[str, dict[str, str]] = {}


def register_integration(
    name: str,
    factory: Factory,
    *,
    kind: str = "integration",
    description: str = "",
) -> None:
    key = name.strip().lower()
    if not key:
        raise ValueError("empty integration name")
    _REGISTRY[key] = factory
    _META[key] = {"kind": kind, "description": description or name}


def get_integration(name: str) -> Factory | None:
    return _REGISTRY.get(name.strip().lower())


def list_integrations() -> list[dict[str, str]]:
    return [
        {"name": k, **_META.get(k, {})}
        for k in sorted(_REGISTRY)
    ]


def invoke(name: str, *args: Any, **kwargs: Any) -> Any:
    factory = get_integration(name)
    if factory is None:
        raise KeyError(f"unknown integration: {name}")
    return factory(*args, **kwargs)


def _register_builtins() -> None:
    if _REGISTRY:
        return

    def _gpu(**_kw):
        from lib.adapters.integrations import gpu

        return gpu

    def _external(**_kw):
        from lib.adapters.integrations import external_tools

        return external_tools

    def _n8n(**_kw):
        from lib.adapters.integrations import n8n

        return n8n

    def _comfy(**_kw):
        from lib.adapters.integrations import comfyui

        return comfyui

    register_integration("gpu", _gpu, kind="gpu", description="ComfyUI/Ollama VRAM coordinator")
    register_integration("external_tools", _external, kind="workflow", description="Coze/Dify/webhook tools")
    register_integration("n8n", _n8n, kind="workflow", description="n8n bridge")
    register_integration("comfyui", _comfy, kind="image", description="ComfyUI HTTP client")


_register_builtins()
