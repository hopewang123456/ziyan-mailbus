"""Internal LLM 配置解析（env 占位符、provider 标准化视图）。"""

from __future__ import annotations

import os
from copy import deepcopy

from lib.infra.utils import json_read

# protocol 归一：旧 kind / openai_compatible 别名统一到三态 + stub
_PROTOCOL_ALIASES = {
    "openai": "openai",
    "openai_compatible": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "stub": "stub",
}


def _normalize_protocol(pc: dict, name: str) -> str:
    raw = (pc.get("protocol") or pc.get("kind") or "").strip().lower()
    if raw in _PROTOCOL_ALIASES:
        return _PROTOCOL_ALIASES[raw]
    if name == "stub":
        return "stub"
    # 缺省按 openai 兼容端点处理（最通用）
    return "openai"


def _api_key_configured(pc: dict) -> bool:
    api_key = pc.get("api_key") or ""
    if api_key and api_key != "***":
        return True
    env_key = pc.get("api_key_env") or ""
    return bool(env_key and os.environ.get(env_key))


def resolve_llm_config(raw: dict) -> dict:
    cfg = deepcopy(raw or {})
    providers = cfg.get("providers") or {}
    for name, pc in list(providers.items()):
        if not isinstance(pc, dict):
            continue
        env_key = pc.get("api_key_env")
        if env_key and not pc.get("api_key"):
            val = os.environ.get(env_key)
            if val:
                pc = dict(pc)
                pc["api_key"] = val
                providers[name] = pc
    cfg["providers"] = providers
    return cfg


def provider_view(raw: dict, data_dir: str = "") -> dict:
    """合并 seed（config/llm/internal-llm.json）providers 与 store providers。

    返回标准化视图：逐 provider 补 protocol（三态）+ api_key_configured（只读派生），
    并掩码 api_key。store 优先于 seed，seed 中缺失的 provider 会被带出（保证已配置项可见）。
    """
    from lib.infra.constants import MAILBUS_ROOT

    cfg = deepcopy(raw or {})
    providers = dict(cfg.get("providers") or {})

    seed_path = os.path.join(str(MAILBUS_ROOT), "config", "llm", "internal-llm.json")
    seed = json_read(seed_path, {}) or {}
    for name, spc in (seed.get("providers") or {}).items():
        if isinstance(spc, dict) and name not in providers:
            providers[name] = deepcopy(spc)
    if not cfg.get("provider_priority") and seed.get("provider_priority"):
        cfg["provider_priority"] = list(seed["provider_priority"])

    for name, pc in providers.items():
        if not isinstance(pc, dict):
            continue
        pc["protocol"] = _normalize_protocol(pc, name)
        pc["api_key_configured"] = _api_key_configured(pc)
        if pc.get("api_key"):
            pc["api_key"] = "***"

    cfg["providers"] = providers
    return cfg
