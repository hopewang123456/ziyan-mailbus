"""mailbus_internal_llm 配置解析 — env 覆盖 + Docker 内 Ollama 地址。

Ollama 为外部 local provider：mailbus 仅解析 base_url/model 并走官方 API；
不在此模块内嵌入或修改 Ollama 实现。
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict


def _docker_ollama_host(base: str) -> str:
    """容器内访问宿主机 Ollama。"""
    if not os.path.exists("/.dockerenv"):
        return base
    for host in ("127.0.0.1", "localhost"):
        if host in base:
            return base.replace(host, "host.docker.internal")
    return base


def resolve_provider(name: str, pc: dict) -> dict:
    out = dict(pc or {})
    base_env = (pc or {}).get("base_url_env") or (
        "MAILBUS_OLLAMA_BASE_URL" if name == "local" else None
    )
    if base_env:
        override = os.environ.get(base_env, "").strip()
        if override:
            out["base_url"] = override.rstrip("/")
    elif name == "local" and (pc or {}).get("kind") == "ollama":
        out["base_url"] = _docker_ollama_host(
            (pc or {}).get("base_url") or "http://127.0.0.1:11434",
        ).rstrip("/")

    model_env = (pc or {}).get("model_env") or (
        "MAILBUS_OLLAMA_MODEL" if name == "local" else None
    )
    if model_env:
        model_override = os.environ.get(model_env, "").strip()
        if model_override:
            out["model"] = model_override

    return out


def resolve_llm_config(raw: dict | None) -> dict:
    """合并 env · 解析 provider；默认 priority 为 local → remote。"""
    from ..env_bootstrap import load_mailbus_env

    load_mailbus_env()
    if not raw:
        return {}
    cfg: Dict[str, Any] = copy.deepcopy(raw)
    cfg.setdefault("provider_priority", ["local", "remote"])

    priority_env = os.environ.get("MAILBUS_INTERNAL_LLM_PROVIDER_PRIORITY", "").strip()
    if priority_env:
        cfg["provider_priority"] = [p.strip() for p in priority_env.split(",") if p.strip()]

    providers = cfg.get("providers") or {}
    cfg["providers"] = {name: resolve_provider(name, pc) for name, pc in providers.items()}
    cfg["_resolved"] = True
    return cfg
