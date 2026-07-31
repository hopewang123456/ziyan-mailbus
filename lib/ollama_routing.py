"""Ollama 本地路由 — 与 smart_routing / mailbus_internal_llm 共用配置与探测。"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from .model_router import TIER_FLASH, TIER_OLLAMA

_PROBE_CACHE: dict[str, Any] = {"at": 0.0, "ready": False, "model": "", "base_url": ""}
_PROBE_TTL_SEC = 30.0


def _mail_root() -> str:
    from .constants import MAILBUS_ROOT
    return MAILBUS_ROOT


def resolve_ollama_settings(config: Optional[dict] = None, data_dir: str = "") -> dict:
    """Resolve Ollama base_url/model via service_registry (+ legacy llm aliases)."""
    from .service_registry import service_settings

    settings = service_settings("ollama", config=config, data_dir=data_dir)
    # Legacy mailbus_internal_llm.providers.local may still override model if services empty
    if config and not (settings.get("model") or "").strip():
        providers = (config.get("mailbus_internal_llm") or {}).get("providers") or {}
        for name, pc in providers.items():
            if not isinstance(pc, dict):
                continue
            if (pc.get("kind") or name) == "ollama" or name == "local":
                if pc.get("model"):
                    settings["model"] = pc["model"]
                break
    return {
        "base_url": settings["base_url"],
        "model": settings.get("model") or "qwen2.5:3b-instruct-q4_K_M",
        "timeout_seconds": int(settings.get("timeout_seconds") or 60),
    }


def is_ollama_ready(
    config: Optional[dict] = None,
    *,
    data_dir: str = "",
    force_refresh: bool = False,
) -> bool:
    """Ollama /api/tags 可达且目标 model 存在（带短 TTL 缓存）。"""
    now = time.monotonic()
    if not force_refresh and now - float(_PROBE_CACHE.get("at") or 0) < _PROBE_TTL_SEC:
        return bool(_PROBE_CACHE.get("ready"))

    settings = resolve_ollama_settings(config, data_dir)
    from .internal_llm.probe import _probe_ollama

    probe = _probe_ollama(settings)
    ready = bool(probe.get("ok") and probe.get("model_available", True))
    _PROBE_CACHE.update({
        "at": now,
        "ready": ready,
        "model": settings["model"],
        "base_url": settings["base_url"],
    })
    return ready


def agent_supports_ollama(agent_cfg: dict, agent_types: dict) -> bool:
    atype = (agent_cfg or {}).get("type") or ""
    models_map = (agent_types or {}).get("models") or {}
    ollama_entry = models_map.get(TIER_OLLAMA) or {}
    return bool(ollama_entry.get(atype))


def ollama_model_flag(
    atype: str,
    *,
    config: Optional[dict] = None,
    data_dir: str = "",
    agent_types: Optional[dict] = None,
) -> str:
    """按框架生成 Ollama CLI 参数；无映射则返回空串。"""
    settings = resolve_ollama_settings(config, data_dir)
    model = settings["model"]
    templates = (agent_types or {}).get("models", {}).get(TIER_OLLAMA) or {}
    tpl = templates.get(atype) or ""
    if not tpl:
        return ""
    if "{model}" in tpl:
        return tpl.replace("{model}", model)
    return tpl


def prepare_gpu_for_ollama_push(config: Optional[dict]) -> dict:
    """推送前释放 ComfyUI 显存，便于 Ollama 使用本机 GPU（不长期占锁）。"""
    from lib.adapters.integrations.gpu import load_gpu_sharing_config, release_comfyui_vram

    gs = load_gpu_sharing_config(config)
    if not gs.get("enabled") or not gs.get("release_comfyui_before_llm"):
        return {"skipped": True}
    return release_comfyui_vram(gs["comfyui_base_url"])


def invalidate_ollama_probe_cache() -> None:
    _PROBE_CACHE["at"] = 0.0
